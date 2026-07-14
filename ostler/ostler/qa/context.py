"""Deterministic changed-code to OKF obligation mapping."""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler import graph as graph_mod
from ostler import markdown
from ostler.model import Graph, _parse_ui_nodes, load

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_SYMBOL_RE = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|function|func|fn)\s+([A-Za-z_$][\w$]*)"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="
)
_AC_RE = re.compile(r"^(?:AC\s*)?(\d+)\s*[:.)-]\s*(.+)$", re.IGNORECASE)


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
    features_root: str = "docs/features",
    story_file: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    source_roots = source_roots or {}
    base_graph = _graph_at_revision(root, base, features_root)
    head_graph = load(root) if head == "WORKTREE" else _graph_at_revision(root, head, features_root)
    changes = _changed_units(root, base, head, source_roots)
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
        mapped = False
        for node_id, node in nodes_by_id.items():
            code_refs = _values(node.get("bullets", {}).get("code"))
            exact = sorted(refs.intersection({_normalize_code_ref(item) for item in code_refs}))
            file_owned = [
                item
                for item in code_refs
                if _code_path(item) in {change.base_path, change.head_path}
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
        if source in journeys and target in nodes_by_id:
            contracts.add(target)
            direct_reasons.setdefault(target, []).append(
                {"kind": "flow-contract-closure", "ref": source}
            )

    relation_keys = (
        "consistency",
        "consistency rule",
        "consistency group",
        "persistence",
        "event",
        "concurrency",
        "idempotency",
    )
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

    verification_refs: list[dict[str, str]] = []
    for node_id in sorted(contracts | journeys):
        node = nodes_by_id[node_id]
        code_refs = _values(node.get("bullets", {}).get("code"))
        for ref in code_refs:
            normalized = _normalize_code_ref(ref)
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
        for ref in _values(nodes_by_id[node_id].get("bullets", {}).get("verify")):
            verification_refs.append({"node": node_id, "ref": _normalize_code_ref(ref)})
        if not _values(node.get("bullets", {}).get("verify")):
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
            nodes_by_id[node_id], direct_reasons.get(node_id, []), journey=False
        )
    ] + [
        obligation
        for node_id in sorted(journeys)
        for obligation in _obligations(
            nodes_by_id[node_id], direct_reasons.get(node_id, []), journey=True
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
        "healthFindings": health,
        "acceptanceCriteria": _acceptance_criteria(story_file),
        "obligations": obligations,
    }


def write_context(packet: dict[str, Any], spec_dir: Path) -> tuple[Path, Path]:
    spec_dir.mkdir(parents=True, exist_ok=True)
    json_path = spec_dir / "qa-okf-context.json"
    md_path = spec_dir / "qa-okf-context.md"
    json_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_context(packet), encoding="utf-8")
    return json_path, md_path


def render_context(packet: dict[str, Any]) -> str:
    lines = [
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
        lines.append(f"- `{obligation['id']}`: {obligation['requirement']}")
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
    old_path = new_path = ""
    for line in diff.splitlines():
        if line.startswith("--- "):
            old_path = line[4:].removeprefix("a/")
        elif line.startswith("+++ "):
            new_path = line[4:].removeprefix("b/")
            path = new_path if new_path != "/dev/null" else old_path
            units.setdefault(path, {"base": set(), "head": set(), "old": old_path, "new": new_path})
        elif match := _HUNK_RE.match(line):
            path = new_path if new_path != "/dev/null" else old_path
            unit = units[path]
            base_start, base_count = int(match[1]), int(match[2] or 1)
            head_start, head_count = int(match[3]), int(match[4] or 1)
            unit["base"].update(range(base_start, base_start + base_count))
            unit["head"].update(range(head_start, head_start + head_count))
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
                base_symbols=tuple(_symbols_for_lines(base_text, item["base"])),
                head_symbols=tuple(_symbols_for_lines(head_text, item["head"])),
            )
        )
    return output


def _symbols_for_lines(text: str, lines: set[int]) -> list[str]:
    if not text or not lines:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
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
        for number, line in enumerate(text.splitlines(), start=1):
            match = _SYMBOL_RE.match(line)
            if match:
                current = match.group(1) or match.group(2) or ""
                symbols.append((number, number, current))
    found: set[str] = set()
    for line in lines:
        containing = [item for item in symbols if item[0] <= line <= item[1]]
        if containing:
            found.add(max(containing, key=lambda item: item[0])[2])
    return sorted(found)


def _revision_text(root: Path, revision: str, path: str) -> str:
    if not path or path == "/dev/null":
        return ""
    try:
        return _git(root, "show", f"{revision}:{path}")
    except RuntimeError:
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
    for text in texts:
        all_lines = set(range(1, len(text.splitlines()) + 1))
        if symbol in _symbols_for_lines(text, all_lines):
            return True
    return False


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


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


def _normalize_code_ref(value: str) -> str:
    return value.strip().strip("`, ")


def _code_path(value: str) -> str:
    return _normalize_code_ref(value).partition("::")[0]


def _surface_owner(path: str, roots: dict[str, list[str]]) -> str:
    matches = [
        (len(prefix.rstrip("/")), surface)
        for surface, prefixes in roots.items()
        for prefix in prefixes
        if path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")
    ]
    return max(matches)[1] if matches else ""


def _obligations(
    node: dict[str, Any],
    reasons: list[dict[str, str]],
    *,
    journey: bool,
) -> list[dict[str, Any]]:
    suffix = "end-state" if journey else "contract"
    base = {
        "id": f"okf:{node['id']}:{suffix}",
        "kind": "journey" if journey else "contract",
        "node": node["id"],
        "source": node["path"],
        "requirement": node.get("title") or node["id"],
        "evidenceRequired": "live",
        "reasons": reasons or [{"kind": "graph-closure", "ref": node["id"]}],
    }
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
