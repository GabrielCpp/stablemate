"""Deterministic changed-code to OKF obligation mapping."""

from __future__ import annotations

import ast
import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from ostler import graph as graph_mod
from ostler import inventory, markdown, path as path_mod, refs as refs_mod, registry
from ostler.model import Graph, _parse_ui_nodes, load

#: The last-resort declaration shape, for a language with no parser and no entry in
#: `inventory` — and for a Python file `ast` could not read. Declared in
#: `scripts/check_parsers.py` for that reason: it is the fallback, never the first answer.
_SYMBOL_RE = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|function|func|fn)\s+([A-Za-z_$][\w$]*)"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="
)
_AC_RE = re.compile(r"^(?:AC\s*)?(\d+)\s*[:.)-]\s*(.+)$", re.IGNORECASE)
_VERIFY_REF_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_./$-]+\.(?:py|tsx?|jsx?|go|mjs|cjs|ya?ml|dart|java|kts?|rs|sh|bash|sql|rb|php|cs|swift|feature))"
    r"(?:::(?P<symbol>[^`,]+))?"
)

#: Bullets the relation fixpoint joins nodes on. A node naming the same consistency group,
#: persistence store, event or idempotency key as an already-selected node is pulled in.
_RELATION_KEYS = (
    "consistency",
    "consistency rule",
    "consistency group",
    "persistence",
    "event",
    "concurrency",
    "idempotency",
)

#: The reason kind the fixpoint stamps for each of those bullets.
_RELATION_REASON_KINDS = frozenset(key.replace(" ", "-") for key in _RELATION_KEYS)

#: Reason kinds that reach a node only through the graph, never through the diff. A node
#: held solely by these was not touched by this story — the closure walked to it from
#: something that was. It stays in the packet as context and is not owed live evidence.
#:
#: The second group is the relation fixpoint below (`while related:`), which walks
#: `emits`/`consumes` and the consistency/persistence/concurrency bullets until nothing new
#: is reachable. That loop never reads the diff — it is closure by construction, and every
#: kind it mints belongs here. Leaving them out is what made a seven-criterion story owe
#: live proof against sixty-seven documents.
_CLOSURE_REASON_KINDS = frozenset(
    {
        "contains-impacted-node",
        "flow-links-contract",
        "flow-contract-closure",
        "graph-closure",
        "event-consumer",
        "event-producer",
    }
    | _RELATION_REASON_KINDS
)

#: Bullets that name how to address a node in a running UI. Lifted onto the obligation so a
#: planner writing a browser locator reads them there rather than re-deriving them from the
#: sibling `role:`/`name:` obligations it happens to have been handed.
_LOCATOR_KEYS = ("selector", "role", "name", "keyboard", "route", "entry", "params")

_QA_REQUIREMENT_KEYS = {
    "flow": ("start", "end"),
    "component": ("role", "name", "keyboard", "states"),
    "command": ("does",),
    "endpoint": ("does", "status", "statuses", "error", "errors", "auth", "authorization"),
    "interaction": ("when", "does", "keyboard"),
    "invocation": (
        "when",
        "does",
        "status",
        "statuses",
        "error",
        "errors",
        "auth",
        "authorization",
    ),
    "method": ("returns", "raises"),
    "field": ("required", "default", "semantics"),
}


@dataclass(frozen=True)
class ChangedUnit:
    path: str
    base_path: str
    head_path: str
    status: str
    base_lines: tuple[int, ...]
    head_lines: tuple[int, ...]
    base_symbols: tuple[str, ...]
    head_symbols: tuple[str, ...]


def build_context(
    root: Path,
    *,
    base: str,
    head: str = "WORKTREE",
    source_roots: dict[str, list[str]] | None = None,
    features_root: str = "",
    story_file: Path | None = None,
    exclude_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Map a `base..head` code diff onto the OKF graph and return the obligation packet.

    `exclude_paths` are repo-relative paths to drop from the diff before anything is
    obligated on them. It exists for the `head="WORKTREE"` caller: the worktree is not a
    commit, so it can hold work that belongs to whoever left it there rather than to the
    change under examination, and only that caller can tell the two apart.
    """
    root = root.resolve()
    excluded_paths = {str(path) for path in exclude_paths}
    # Repo-relative on purpose: this one is handed to `git ls-tree`, which pathspecs against
    # the work tree, not the filesystem. Empty means "wherever this repo configures its book",
    # which ostler answers — spelling `docs/features` here would read the wrong tree in a repo
    # that moved it.
    features_root = features_root or path_mod.features_root_in(root).relative_to(root).as_posix()
    source_roots = source_roots or {}
    current = load(root)
    base_graph = _graph_at_revision(root, base, features_root)
    head_graph = current if head == "WORKTREE" else _graph_at_revision(root, head, features_root)
    excluded_doc_roots = {
        path.resolve().relative_to(root).as_posix()
        for path in current.doc_roots.values()
        if path.resolve().is_relative_to(root)
    }
    changes = [
        change
        for change in _changed_units(root, base, head, source_roots)
        if change.path not in excluded_paths
        and not any(
            change.path == prefix or change.path.startswith(prefix.rstrip("/") + "/")
            for prefix in excluded_doc_roots
        )
        and not _is_non_production_path(change.path)
        and not _is_generated_unit(root, change)
    ]
    base_nodes, base_edges = _serialized_graph(base_graph)
    head_nodes, head_edges = _serialized_graph(head_graph)
    nodes_by_id = _merge_snapshot_nodes(base_nodes, head_nodes)

    direct_reasons: dict[str, list[dict[str, str]]] = {}
    health: list[dict[str, Any]] = []
    changed_code: list[dict[str, Any]] = []
    for change in changes:
        refs = {
            *(
                f"{change.base_path}::{symbol}"
                for symbol in change.base_symbols
                if change.base_path
            ),
            *(
                f"{change.head_path}::{symbol}"
                for symbol in change.head_symbols
                if change.head_path
            ),
        }
        changed_code.append(
            {
                "path": change.path,
                "basePath": change.base_path,
                "headPath": change.head_path,
                "status": change.status,
                "baseLines": list(change.base_lines),
                "headLines": list(change.head_lines),
                "baseSymbols": list(change.base_symbols),
                "headSymbols": list(change.head_symbols),
            }
        )
        mapped = change.status == "deleted"
        for node_id, node in nodes_by_id.items():
            cited = refs_mod.code_refs(node.get("bullets", {}).get("code"))
            exact = sorted(refs.intersection(cited))
            file_owned = [
                item
                for item in cited
                if refs_mod.ref_path(item) in {change.base_path, change.head_path}
            ]
            if exact:
                mapped = True
                for ref in exact:
                    direct_reasons.setdefault(node_id, []).append(
                        {"kind": "changed-code", "ref": ref}
                    )
            elif file_owned:
                mapped = True
                direct_reasons.setdefault(node_id, []).append(
                    {"kind": "file-owner", "ref": change.path}
                )
        if not mapped:
            surface = _surface_owner(change.path, source_roots)
            surface_nodes = [
                node_id
                for node_id, node in nodes_by_id.items()
                if surface and node.get("surface") == surface
            ]
            if surface_nodes:
                mapped = True
                for node_id in surface_nodes:
                    direct_reasons.setdefault(node_id, []).append(
                        {"kind": "surface-owner", "ref": f"{surface}:{change.path}"}
                    )
            else:
                health.append(
                    {
                        "kind": "unmapped-change",
                        "severity": "error",
                        "path": change.path,
                        "message": "changed production unit has no exact symbol, file, or surface owner",
                    }
                )

    # A bare-file `code:` citation says "this node is documented against that file". It
    # localizes a change to the node only while the node is the file's *sole* owner. A
    # global stylesheet or a shared module is cited by every node that renders through it,
    # so one edited line makes all of them file-owned — and none of that is evidence the
    # change touched any particular one. Which of those citations are shared is a property
    # of the whole change set, so it is known here and not inside the loop above.
    file_owners: dict[str, set[str]] = {}
    for node_id, reasons in direct_reasons.items():
        for reason in reasons:
            if reason["kind"] == "file-owner":
                file_owners.setdefault(reason["ref"], set()).add(node_id)
    shared_files = {ref for ref, owners in file_owners.items() if len(owners) > 1}

    # Containment and graph links broaden impact without lexical inference.
    impacted = set(direct_reasons)
    for node_id in list(impacted):
        parent = nodes_by_id.get(node_id, {}).get("parent")
        while parent and parent in nodes_by_id:
            if parent not in impacted:
                direct_reasons.setdefault(parent, []).append(
                    {"kind": "contains-impacted-node", "ref": node_id}
                )
            impacted.add(parent)
            parent = nodes_by_id[parent].get("parent")
    edges = base_edges | head_edges
    flows = {node_id for node_id, node in nodes_by_id.items() if node.get("type") == "flow"}
    journeys = set(impacted & flows)
    for source, target in edges:
        if source in flows and target in impacted:
            journeys.add(source)
            direct_reasons.setdefault(source, []).append(
                {"kind": "flow-links-contract", "ref": target}
            )
    contracts = impacted - flows
    for source, target in edges:
        # A flow target is somebody else's journey, never this closure's contract. The two
        # sets are disjoint by construction one line up, and `_obligations` relies on it:
        # it runs once per member, and a node in both is walked twice. Only the *base*
        # obligation carries the role in its id (`:contract` vs `:end-state`), so the
        # collision surfaces on the bullet-derived ones — a flow filed both ways emits
        # `:start:1` and `:end:1` twice, `validate_context` reports duplicate ids, and the
        # documentation gate hands the author a rework brief for a defect that is not in
        # the book and that no amount of writing can clear.
        if source in journeys and target in nodes_by_id and target not in flows:
            contracts.add(target)
            direct_reasons.setdefault(target, []).append(
                {"kind": "flow-contract-closure", "ref": source}
            )

    relation_keys = _RELATION_KEYS
    related = True
    while related:
        related = False
        selected = contracts | journeys
        emitted = {
            value
            for node_id in selected
            for value in _values(nodes_by_id[node_id].get("bullets", {}).get("emits"))
        }
        consumed = {
            value
            for node_id in selected
            for value in _values(nodes_by_id[node_id].get("bullets", {}).get("consumes"))
        }
        relation_values = {
            value
            for node_id in selected
            for key in relation_keys
            for value in _values(nodes_by_id[node_id].get("bullets", {}).get(key))
        }
        for node_id, node in nodes_by_id.items():
            if node_id in selected:
                continue
            bullets = node.get("bullets", {})
            reasons: list[dict[str, str]] = []
            for value in _values(bullets.get("consumes")):
                if value in emitted:
                    reasons.append({"kind": "event-consumer", "ref": value})
            for value in _values(bullets.get("emits")):
                if value in consumed:
                    reasons.append({"kind": "event-producer", "ref": value})
            for key in relation_keys:
                for value in _values(bullets.get(key)):
                    if value in relation_values:
                        reasons.append({"kind": key.replace(" ", "-"), "ref": value})
            if reasons:
                (journeys if node.get("type") == "flow" else contracts).add(node_id)
                direct_reasons.setdefault(node_id, []).extend(reasons)
                related = True

    selected = contracts | journeys
    verification_index: list[dict[str, Any]] = []
    for node_id, node in sorted(nodes_by_id.items()):
        for ref in _verification_refs(node):
            verification_index.append(
                {"node": node_id, "ref": ref, "path": _code_path(ref), "impacted": node_id in selected}
            )
    verification_refs = [
        {"node": item["node"], "ref": item["ref"], "path": item["path"]}
        for item in verification_index
        if item["impacted"]
    ]
    grounded: set[str] = set()
    for node_id in sorted(selected):
        node = nodes_by_id[node_id]
        for normalized in refs_mod.code_refs(node.get("bullets", {}).get("code")):
            if not _grounding_exists(root, base, head, normalized):
                health.append(
                    {
                        "kind": "dangling-grounding",
                        "severity": "error",
                        "node": node_id,
                        "ref": normalized,
                        "message": "code grounding resolves in neither base nor head",
                    }
                )
            else:
                grounded.add(node_id)
        if not _verification_refs(node):
            health.append(
                {
                    "kind": "missing-verification",
                    "severity": "warning",
                    "node": node_id,
                    "message": "impacted contract has no grounded verify reference",
                }
            )
    obligations = [
        obligation
        for node_id in sorted(contracts)
        for obligation in _obligations(
            nodes_by_id[node_id],
            direct_reasons.get(node_id, []),
            journey=False,
            required=_is_required(node_id, direct_reasons, grounded, shared_files),
        )
    ] + [
        obligation
        for node_id in sorted(journeys)
        for obligation in _obligations(
            nodes_by_id[node_id],
            direct_reasons.get(node_id, []),
            journey=True,
            required=_is_required(node_id, direct_reasons, grounded, shared_files),
        )
    ]
    obligations.sort(key=lambda item: item["id"])
    return {
        "version": 1,
        "available": bool(nodes_by_id),
        "base": base,
        "head": head,
        "changedCode": changed_code,
        "directNodes": [
            {"node": node_id, "reasons": direct_reasons[node_id]}
            for node_id in sorted(direct_reasons)
        ],
        "contracts": sorted(contracts),
        "journeys": sorted(journeys),
        "journeyNodes": sorted(journeys),
        "verificationRefs": verification_refs,
        "verificationIndex": verification_index,
        "healthFindings": health,
        "acceptanceCriteria": _acceptance_criteria(story_file),
        "obligations": obligations,
    }


#: The whole-book verification table, split out of the agent-facing packet. It carries one
#: row per `verify:` ref in the entire feature graph — impacted or not — because
#: `_attribute_failures` classifies a failing test as "outside-impact" rather than
#: "unattributed" only when it can find a non-impacted owner. That makes it the largest
#: member of the packet by far and the least useful to a reader: on a nine-epic book it was
#: 61% of a 676 KB file that a planning agent reads in full. The reader keeps
#: `verificationRefs` — the impacted subset — and the machine reads this beside it.
VERIFICATION_INDEX_FILE = "qa-okf-verification-index.json"


def write_context(packet: dict[str, Any], spec_dir: Path) -> tuple[Path, Path]:
    spec_dir.mkdir(parents=True, exist_ok=True)
    json_path = spec_dir / "qa-okf-context.json"
    md_path = spec_dir / "qa-okf-context.md"
    reader_packet = {key: value for key, value in packet.items() if key != "verificationIndex"}
    (spec_dir / VERIFICATION_INDEX_FILE).write_text(
        json.dumps(packet.get("verificationIndex", []), indent=2) + "\n", encoding="utf-8"
    )
    json_path.write_text(json.dumps(reader_packet, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_context(reader_packet), encoding="utf-8")
    return json_path, md_path


def render_context(packet: dict[str, Any]) -> str:
    lines = [
        "---",
        f"type: {registry.spec_type_for('qa-okf-context.md')}",
        "---",
        "# QA OKF Context",
        "",
        f"- Base: `{packet.get('base', '')}`",
        f"- Head: `{packet.get('head', '')}`",
        f"- Available: `{str(packet.get('available', False)).lower()}`",
        "",
        "## Changed Code",
        "",
    ]
    for change in packet.get("changedCode", []):
        symbols = sorted(set(change.get("baseSymbols", []) + change.get("headSymbols", [])))
        lines.append(f"- `{change['path']}` ({change['status']}): {', '.join(symbols) or 'file scope'}")
    if not packet.get("changedCode"):
        lines.append("- (none)")
    lines.extend(["", "## Obligations", ""])
    for obligation in packet.get("obligations", []):
        suffix = "" if obligation.get("required", True) else "  _(context only — not owed evidence)_"
        lines.append(f"- `{obligation['id']}`: {obligation['requirement']}{suffix}")
        for key, values in sorted(obligation.get("locators", {}).items()):
            lines.append(f"  - {key}: {'; '.join(values)}")
    if not packet.get("obligations"):
        lines.append("- (none)")
    lines.extend(["", "## Health Findings", ""])
    for finding in packet.get("healthFindings", []):
        lines.append(f"- **{finding['kind']}** `{finding.get('path', '')}`: {finding['message']}")
    if not packet.get("healthFindings"):
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


def validate_context(packet: Any) -> list[str]:
    if not isinstance(packet, dict):
        return ["context must be a JSON object"]
    problems: list[str] = []
    if packet.get("version") != 1:
        problems.append("context.version must be 1")
    if not isinstance(packet.get("available"), bool):
        problems.append("context.available must be boolean")
    for field in ("changedCode", "directNodes", "contracts", "journeys", "journeyNodes", "verificationRefs", "healthFindings", "obligations"):
        if not isinstance(packet.get(field), list):
            problems.append(f"context.{field} must be a list")
    if "verificationIndex" in packet and not isinstance(packet["verificationIndex"], list):
        problems.append("context.verificationIndex must be a list")
    seen: set[str] = set()
    for item in packet.get("obligations", []):
        if not isinstance(item, dict) or not item.get("id"):
            problems.append("every obligation must be an object with an id")
            continue
        if item["id"] in seen:
            problems.append(f"duplicate obligation id '{item['id']}'")
        seen.add(item["id"])
    return problems


def _graph_at_revision(root: Path, revision: str, features_root: str) -> Graph:
    current = load(root)
    graph = Graph(
        root=root,
        org_name=current.org_name,
        profile=current.profile,
        doc_roots={**current.doc_roots, "features": root / features_root},
    )
    result = _git(root, "ls-tree", "-r", "--name-only", revision, "--", features_root)
    for rel in sorted(line for line in result.splitlines() if line.endswith(".md")):
        try:
            text = _git(root, "show", f"{revision}:{rel}")
        except RuntimeError:
            continue
        graph.ui_nodes.extend(_parse_ui_nodes(markdown.split(text), root / rel, root))
    return graph


def _serialized_graph(graph: Graph) -> tuple[dict[str, dict[str, Any]], set[tuple[str, str]]]:
    data = graph_mod.build(graph)
    nodes = {item["id"]: item for item in data["nodes"]}
    edges = {(item["from"], item["to"]) for item in data["edges"] if item.get("to")}
    return nodes, edges


def _changed_units(
    root: Path,
    base: str,
    head: str,
    source_roots: dict[str, list[str]],
) -> list[ChangedUnit]:
    args = ["diff", "--find-renames", "--unified=0", base]
    if head != "WORKTREE":
        args.append(head)
    configured = sorted({path for paths in source_roots.values() for path in paths})
    if configured:
        args.extend(["--", *configured])
    diff = _git(root, *args)
    units: dict[str, dict[str, Any]] = {}
    for patched in _patch_set(diff):
        old_path = patched.source_file.removeprefix("a/")
        new_path = patched.target_file.removeprefix("b/")
        path = new_path if new_path != "/dev/null" else old_path
        unit = units.setdefault(
            path, {"base": set(), "head": set(), "old": old_path, "new": new_path}
        )
        for hunk in patched:
            unit["base"].update(range(hunk.source_start, hunk.source_start + hunk.source_length))
            unit["head"].update(range(hunk.target_start, hunk.target_start + hunk.target_length))
    name_args = ["diff", "--find-renames", "--name-status", base]
    if head != "WORKTREE":
        name_args.append(head)
    if configured:
        name_args.extend(["--", *configured])
    for line in _git(root, *name_args).splitlines():
        fields = line.split("\t")
        status_code = fields[0]
        if status_code.startswith("R") and len(fields) >= 3:
            old, new = fields[1], fields[2]
        elif len(fields) >= 2:
            old = "/dev/null" if status_code == "A" else fields[1]
            new = "/dev/null" if status_code == "D" else fields[1]
        else:
            continue
        path = new if new != "/dev/null" else old
        units.setdefault(path, {"base": set(), "head": set(), "old": old, "new": new})
    if head == "WORKTREE":
        untracked_args = ["ls-files", "--others", "--exclude-standard"]
        if configured:
            untracked_args.extend(["--", *configured])
        for path in _git(root, *untracked_args).splitlines():
            text = _working_text(root, path)
            units.setdefault(
                path,
                {
                    "base": set(),
                    "head": set(range(1, len(text.splitlines()) + 1)),
                    "old": "/dev/null",
                    "new": path,
                },
            )
    output: list[ChangedUnit] = []
    for path, item in sorted(units.items()):
        base_text = _revision_text(root, base, item["old"])
        head_text = (
            _working_text(root, item["new"])
            if head == "WORKTREE"
            else _revision_text(root, head, item["new"])
        )
        if not base_text and not head_text:
            # Nothing readable on either side: a compiled artifact, a binary asset, or an empty
            # file. None of the three can be grounded — there is no symbol to cite and no
            # behaviour to verify — so leaving them in only makes the ownership gate unwinnable,
            # the same failure mode `_is_generated_unit` exists to prevent. A *deleted source*
            # file is not caught here: its base side still reads as text, and losing a
            # documented symbol is a real obligation.
            continue
        status = "modified"
        if item["old"] == "/dev/null":
            status = "added"
        elif item["new"] == "/dev/null":
            status = "deleted"
        elif item["old"] != item["new"]:
            status = "renamed"
        output.append(
            ChangedUnit(
                path=path,
                base_path="" if item["old"] == "/dev/null" else item["old"],
                head_path="" if item["new"] == "/dev/null" else item["new"],
                status=status,
                base_lines=tuple(sorted(item["base"])),
                head_lines=tuple(sorted(item["head"])),
                base_symbols=tuple(_symbols_for_lines(base_text, item["base"], item["old"])),
                head_symbols=tuple(_symbols_for_lines(head_text, item["head"], item["new"])),
            )
        )
    return output


def _patch_set(diff: str) -> PatchSet:
    """The diff, parsed. A malformed patch yields no units rather than a traceback.

    `unidiff` replaces a hand-written `@@ -a,b +c,d @@` matcher plus a pair of `--- `/`+++ `
    line prefixes, which between them carried the file's identity in loop-scoped variables:
    a hunk header appearing before any `+++ ` line — a stray `@@` in a *deleted line's own
    content*, which `--unified=0` still emits — indexed `units` with whatever path the
    previous file left behind, and raised `KeyError` on the very first diff. The parser knows
    a hunk body from a hunk header, so the association is structural.
    """
    try:
        return PatchSet(diff)
    except UnidiffParseError:
        return PatchSet("")


def _symbols_for_lines(text: str, lines: set[int], path: str = "") -> list[str]:
    """The symbols whose bodies span any of *lines* — the diff's changed units.

    Python is parsed (`ostler.inventory`'s front end), which is what makes a symbol's *extent*
    real: an `ast` node knows where its body ends, so a hunk landing in the middle of a
    function is attributed to that function rather than to "the last declaration seen above
    it", which is all the line scan below can offer. The parse is attempted only for Python —
    letting every language fall through to `ast.parse` and relying on `SyntaxError` to reject
    it means a `.js` file that happens to be valid Python (`x = 1`) parses as an empty module
    and silently reports no changed symbols at all.
    """
    if not text or not lines:
        return []
    suffix = Path(path).suffix
    tree = inventory.parse_python(text) if suffix in {".py", ".pyi", ""} else None
    symbols: list[tuple[int, int, str]] = []
    if tree is not None:
        def visit(node: ast.AST, prefix: str = "") -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = f"{prefix}.{child.name}" if prefix else child.name
                    symbols.append((child.lineno, getattr(child, "end_lineno", child.lineno), name))
                    visit(child, name)
                else:
                    visit(child, prefix)

        visit(tree)
    else:
        current = ""
        text_lines = text.splitlines()
        declarations: list[tuple[int, str]] = []
        if suffix == ".go":
            for match in inventory.GO_DECL.finditer(text):
                star, receiver, method, func, typename, value = match.groups()
                if method:
                    owner = f"(*{receiver})" if star else receiver
                    name = f"{owner}.{method}"
                else:
                    name = func or typename or value
                declarations.append((text.count("\n", 0, match.start()) + 1, name))
        elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
            declarations.extend(
                (number, match.group(1))
                for number, line in enumerate(text_lines, start=1)
                if line and not line[:1].isspace()
                if (match := inventory.TS_ANY_DECL.match(line))
            )
        else:
            for number, line in enumerate(text_lines, start=1):
                match = _SYMBOL_RE.match(line)
                if match:
                    current = match.group(1) or match.group(2) or ""
                    declarations.append((number, current))
        symbols.extend(
            (
                start,
                declarations[index + 1][0] - 1
                if index + 1 < len(declarations)
                else len(text_lines),
                name,
            )
            for index, (start, name) in enumerate(declarations)
        )
    found: set[str] = set()
    for line in lines:
        containing = [item for item in symbols if item[0] <= line <= item[1]]
        if containing:
            found.add(max(containing, key=lambda item: item[0])[2])
    return sorted(found)


def _revision_text(root: Path, revision: str, path: str) -> str:
    """The blob's text at `revision`, or "" — the same answer `_working_text` gives for a file
    it cannot decode, so the two sides of a diff agree about what "unreadable" means.

    Binary is not an exotic input here: a repo that committed a compiled artifact and then
    deleted it puts that blob on the base side of the very first diff, and `git show` streams
    its bytes. Decoding those strictly used to raise straight out of `build_context`, so one
    stray executable in the change set voided the whole obligation packet.
    """
    if not path or path == "/dev/null":
        return ""
    try:
        blob = _git_bytes(root, "show", f"{revision}:{path}")
    except RuntimeError:
        return ""
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _working_text(root: Path, path: str) -> str:
    candidate = root / path
    try:
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _grounding_exists(root: Path, base: str, head: str, ref: str) -> bool:
    path, separator, symbol = ref.partition("::")
    texts = [_revision_text(root, base, path)]
    texts.append(
        _working_text(root, path) if head == "WORKTREE" else _revision_text(root, head, path)
    )
    texts = [text for text in texts if text]
    if not texts:
        return False
    if not separator or not symbol or not path.endswith(".py"):
        return True
    # `inventory.declares`, not `_symbols_for_lines`: the two answer different questions and
    # only the first one is grounding's. `_symbols_for_lines` attributes a *diff hunk* to the
    # declaration whose body spans it, so it can only ever report classes and functions — a
    # module-level constant has no body to span. Asking it whether a name exists therefore
    # made every `code:` bullet naming a constant permanently unsatisfiable: the citation was
    # reported dangling in both base and head, and no rewrite of the book could clear it.
    return any(inventory.declares(path, text, symbol) for text in texts)


def _git_bytes(root: Path, *args: str) -> bytes:
    """Raw stdout. Never `text=True`: git's output is only text by convention — `show` streams
    a blob verbatim, and `diff` inlines the bytes of any file git guessed was text — so a
    strict decode inside `subprocess` raises `UnicodeDecodeError` from wherever git was called
    rather than from a place that can decide what an undecodable file means."""
    result = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed")
    return result.stdout


def _git(root: Path, *args: str) -> str:
    """Decoded leniently: every caller but `_revision_text` wants path lists or hunk headers,
    which are ASCII, and would rather see a replacement character inside one line of a diff
    than lose the whole listing. `_revision_text` decodes strictly off `_git_bytes` instead,
    because there "undecodable" has a meaning — no symbols — and "" is how it is spelled."""
    return _git_bytes(root, *args).decode("utf-8", errors="replace")


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


def _merge_snapshot_nodes(
    base: dict[str, dict[str, Any]],
    head: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged = {node_id: {**node, "bullets": dict(node.get("bullets", {}))} for node_id, node in base.items()}
    for node_id, node in head.items():
        if node_id not in merged:
            merged[node_id] = node
            continue
        combined = {**merged[node_id], **node}
        bullets = dict(merged[node_id].get("bullets", {}))
        for key, value in node.get("bullets", {}).items():
            values = [*_values(bullets.get(key)), *_values(value)]
            unique = list(dict.fromkeys(values))
            bullets[key] = unique[0] if len(unique) == 1 else unique
        combined["bullets"] = bullets
        merged[node_id] = combined
    return merged


def _code_path(value: str) -> str:
    return refs_mod.ref_path(refs_mod.normalize_ref(value))


def _verification_refs(node: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for value in _values(node.get("bullets", {}).get("verify")):
        refs.extend(
            f"{match['path']}::{match['symbol'].strip()}"
            if match["symbol"]
            else match["path"]
            for match in _VERIFY_REF_RE.finditer(value)
        )
    return list(dict.fromkeys(refs))


def _surface_owner(path: str, roots: dict[str, list[str]]) -> str:
    matches = [
        (len(prefix.rstrip("/")), surface)
        for surface, prefixes in roots.items()
        for prefix in prefixes
        if prefix.rstrip("/") in ("", ".")
        or path == prefix.rstrip("/")
        or path.startswith(prefix.rstrip("/") + "/")
    ]
    return max(matches)[1] if matches else ""


def _is_non_production_path(path: str) -> bool:
    candidate = path.lower()
    parts = Path(candidate).parts
    non_production_dirs = {
        "test",
        "tests",
        "__tests__",
        "testdata",
        "__snapshots__",
        "snapshots",
        "fixtures",
        "fixture",
        "golden",
        "goldens",
        # QA's own scaffolding. A mock backend, a stub server or a fixture harness exists to
        # make a test runnable; it carries no user-observable behaviour of its own. Treated as
        # production it gets modelled in the book as features, and then every story that so
        # much as touches a mock owes live proof of the mock — QA verifying its own harness
        # instead of the product it was pointed at.
        "mocks",
        "__mocks__",
        "stubs",
        "harness",
        "harnesses",
    }
    if any(part in non_production_dirs for part in parts[:-1]):
        return True
    # Same reasoning, for the directories that name their purpose rather than sit under a
    # conventional folder — `tools/qa-mock-backends/`, `mock-server/`, `qa-fixtures/`.
    if any(
        part.startswith(("qa-mock", "mock-", "mock_", "qa-fixture", "fake-", "fake_"))
        or part.endswith(("-mocks", "-mock-backends", "-fixtures"))
        for part in parts[:-1]
    ):
        return True
    name = parts[-1] if parts else candidate
    if name.startswith("test_") or name.endswith(("_test.py", "_test.go")):
        return True
    if any(token in name for token in (".test.", ".spec.")):
        return True
    if name.endswith(".md") and not any(part in {"prompts", "templates"} for part in parts[:-1]):
        return True
    if name.endswith((".lock", ".rst")) or name in {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "uv.lock",
        "readme.md",
        "changelog.md",
        "license.md",
    }:
        return True
    # Build, dependency-manifest, and tooling-config files. No feature Concept owns these
    # and none should: they carry no user-observable behaviour for QA to verify. Left in,
    # they fail the documentation gate as "unmapped production units" — which is exactly what
    # blocked the first greenfield coder story, whose diff legitimately touched go.mod/go.sum/
    # a Makefile/Pulumi config alongside the real code. Dependency manifests specifically are
    # NOT ignored elsewhere by design (a version bump can change behaviour), but they have no
    # OKF owner, so they belong here for the ownership gate.
    build_config_names = {
        "makefile",
        "dockerfile",
        ".gitignore",
        ".dockerignore",
        "go.mod",
        "go.sum",
        "go.work",
        "go.work.sum",
        "package.json",
        "tsconfig.json",
        "vite.config.ts",
        "pubspec.yaml",
        "pubspec.lock",
        "analysis_options.yaml",
        ".mockery.yaml",
    }
    if name in build_config_names:
        return True
    # Pulumi stack config (Pulumi.yaml, Pulumi.<stack>.yaml).
    if name.startswith("pulumi.") and name.endswith((".yaml", ".yml")):
        return True
    # Log files. Nothing writes one on purpose as a production unit; what lands in a working
    # tree is a tool's debug output — a Firebase/Firestore emulator's `*-debug.log` is the
    # case that reached us, dropped into the repo root by the QA stack the gate itself starts.
    if name.endswith(".log"):
        return True
    # The agent toolchain's own footprint inside a client repo: farrier writes `agents.yml` and
    # the `.agents/` tree, and the coder workflow's QA node writes `qa-stack.yml` (the
    # `manifest_path` default in `coder/qa/nodes/qa.py`). These say how the repo is built and
    # tested *by us* and never what it does for a user, so no feature Concept can own them —
    # and unlike a Makefile they are not even the repo's own scaffolding, they are ours.
    #
    # Left in, the ownership gate reports them as unmapped production units, and the only move
    # left to an agent that must clear the gate is to invent a contract node for them in the
    # product's feature docs. A greenfield run did exactly that: it added a `#tooling` section
    # to `docs/features/api/http/api.md` owning `qa-stack.yml` and friends, which cleared the
    # error and bought a permanent `missing-verification` warning in exchange — a contract that
    # can never have a grounded verify reference, because a stack manifest has no test.
    #
    # Root-scoped on purpose: a nested `agents.yml` is somebody's product file, not ours.
    if len(parts) == 1 and name in {"agents.yml", "qa-stack.yml"}:
        return True
    # The same footprint, at any depth: `okf_builder`'s coverage node writes
    # `.source-inventory.json` *into the source root it scanned*, so there is one per code tree
    # and no root-scoping to lean on. The dotted name is unambiguous enough to stand alone.
    if name == ".source-inventory.json":
        return True
    # CI and agent-tooling dotfile trees.
    return bool(parts and parts[0] in {".github", ".gitlab", ".agents"})


#: How a code generator announces itself. Go standardized the wording and everything that
#: emits Go copies it — protoc, oapi-codegen, mockery, sqlc, ent — and enough tools in other
#: ecosystems copied it too that matching the sentence beats keeping a table of generators.
_GENERATED_MARKER = re.compile(r"^\s*(?://|#|/\*|--|<!--)\s*Code generated .*DO NOT EDIT", re.M)

#: Filename conventions that say the same thing without a marker line, by ecosystem.
_GENERATED_SUFFIXES = (
    ".gen.go",
    ".pb.go",
    ".pb.gw.go",
    ".gen.ts",
    ".gen.tsx",
    ".generated.ts",
    ".g.dart",
    ".gr.dart",
    ".gen.dart",
    ".freezed.dart",
    "_pb2.py",
    "_pb2_grpc.py",
    "_generated.go",
    "_generated.py",
    "_generated.ts",
)

#: Directories whose whole contents are machine-authored.
_GENERATED_DIRS = {"mocks", "__mocks__", "generated", "node_modules", "vendor"}

#: How much of a file to read looking for the marker. It is a header line by convention —
#: the point of the marker is that an editor sees it first — so this is generous already,
#: and bounded because the files it runs against are exactly the enormous ones.
_MARKER_SCAN_BYTES = 4096


def _is_generated_unit(root: Path, change: ChangedUnit) -> bool:
    """Is this changed unit machine-authored, and therefore owned by its generator?

    Generated code is production code — it ships, it serves traffic — but it is not a
    *documentable* unit, and treating it as one is what makes the coder's documentation gate
    unwinnable. `oapi-codegen` alone contributed 26 symbols to one benchmark story's diff,
    among them `UnescapedCookieParamError` and `TooManyValuesForParamError`; grounding those
    means writing OKF nodes for a code generator's internal error types and calling them
    product contracts. The author cannot do it honestly, so it burns every rework pass and
    the story fails on a demand no correct answer satisfies. The contract these files encode
    lives in the thing they were generated *from* — the OpenAPI document, the proto, the
    interface the mock stands in for — and that source is in the diff too, as a real unit.

    Same reasoning as `_is_non_production_path` and the same remedy, kept separate because
    the categories are different: that one is scaffolding that never runs, this one runs and
    is simply not authored by a person.

    The marker scan reads the **worktree**, so a packet built between two revisions relies on
    the naming conventions alone. That is why the conventions are listed rather than left to
    the marker: they cover the generators that dominate real diffs, and a miss here is only
    ever conservative — the unit stays production and the author is asked to ground it.
    """
    lowered = change.path.lower()
    parts = Path(lowered).parts
    if any(part in _GENERATED_DIRS for part in parts[:-1]):
        return True
    if lowered.endswith(_GENERATED_SUFFIXES):
        return True
    # A deletion carries the `/dev/null` sentinel rather than a path; joining it onto `root`
    # would read straight out of the repo, and there is no head file to sniff either way.
    if not change.head_path or Path(change.head_path).is_absolute():
        return False
    try:
        with (root / change.head_path).open("rb") as handle:
            head = handle.read(_MARKER_SCAN_BYTES).decode("utf-8", "replace")
    except OSError:
        return False
    return bool(_GENERATED_MARKER.search(head))


def _is_required(
    node_id: str,
    direct_reasons: dict[str, list[dict[str, str]]],
    grounded: set[str],
    shared_files: frozenset[str] | set[str] = frozenset(),
) -> bool:
    """Whether this node's obligations are owed live evidence, or are only context.

    Three conditions, all from the book rather than from inference. The node must be
    *grounded* — at least one `code:` ref that resolves in base or head — because a node
    whose `code:` is empty documents something nobody has built yet, and a QA plan cannot
    exercise a route or a component that has no implementation. And it must be reached by
    the diff directly rather than only by graph closure, because the closure is deliberately
    broad: a single edited file drags in every flow that links to every contract it owns.
    Demanding live proof for the whole closure is what made the packet grow faster than the
    change did.

    The third is the same argument one level down, for the reach that is *not* closure. A
    `file-owner` reason is a bare-file citation with no symbol behind it, so it points at
    the node only as precisely as the file belongs to it. When several nodes cite the same
    file the citation stops localizing anything — an edit to a global stylesheet owed live
    proof for every component documented against it, which is a plan the change cannot
    justify and the planner cannot write. Those nodes stay in the packet as context; a node
    the diff also reached by an exact symbol keeps its own reason and stays required.
    """
    kinds = {
        reason.get("kind", "")
        for reason in direct_reasons.get(node_id, [])
        if not (reason.get("kind") == "file-owner" and reason.get("ref") in shared_files)
    }
    return node_id in grounded and bool(kinds - _CLOSURE_REASON_KINDS)


def _locators(node: dict[str, Any]) -> dict[str, list[str]]:
    bullets = node.get("bullets", {})
    return {key: _values(bullets.get(key)) for key in _LOCATOR_KEYS if _values(bullets.get(key))}


def _obligations(
    node: dict[str, Any],
    reasons: list[dict[str, str]],
    *,
    journey: bool,
    required: bool = True,
) -> list[dict[str, Any]]:
    suffix = "end-state" if journey else "contract"
    base = {
        "id": f"okf:{node['id']}:{suffix}",
        "kind": "journey" if journey else "contract",
        "node": node["id"],
        "source": node["path"],
        "requirement": node.get("title") or node["id"],
        "required": required,
        "evidenceRequired": "live" if required else "context",
        "reasons": reasons or [{"kind": "graph-closure", "ref": node["id"]}],
    }
    locators = _locators(node)
    if locators:
        base["locators"] = locators
    output = [base]
    normative_keys = (
        "consistency",
        "consistency rule",
        "consistency group",
        "persistence",
        "emits",
        "consumes",
        "concurrency",
        "idempotency",
        *_QA_REQUIREMENT_KEYS.get(str(node.get("type", "")), ()),
    )
    for key in normative_keys:
        for index, requirement in enumerate(_values(node.get("bullets", {}).get(key)), start=1):
            output.append(
                {
                    **base,
                    "id": f"okf:{node['id']}:{key.replace(' ', '-')}:{index}",
                    "kind": key.replace(" ", "-"),
                    "requirement": requirement,
                }
            )
    return output


def _acceptance_criteria(story_file: Path | None) -> list[dict[str, str]]:
    if story_file is None or not story_file.is_file():
        return []
    doc = markdown.split(story_file.read_text(encoding="utf-8"))
    section = doc.find_section("Acceptance Criteria")
    if section is None:
        return []
    criteria: list[dict[str, str]] = []
    for index, bullet in enumerate(section.bullets, start=1):
        text = bullet.text.strip()
        match = _AC_RE.match(text)
        number, requirement = (match.group(1), match.group(2)) if match else (str(index), text)
        criteria.append({"id": f"ac:{number}", "requirement": requirement, "kind": "behavioral"})
    return criteria
