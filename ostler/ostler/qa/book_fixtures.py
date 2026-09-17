"""Book-declared fixtures, walked into the shape the harness executes them from.

`ostler.qa.fixtures` is the agents.yml tier: a fixture that is one named invocation of a
tool this repo already opted into. This module is the *other* tier — a
[`fixture`](../../base-library/library/skills/ostler/okf/references/node-types/fixture.md)
node, a file in the book with its own `## Steps`, `args:`, `provides:`, `needs:` and
`secrets:` bullets. `Qa.fixture()` in the harness checks this tier first and falls back
to the agents.yml one when a name is absent from it.

The harness (`ostler.qa.harness.ostler_qa`) is stdlib-only and cannot import this module,
or anything else outside the standard library — it runs under the *project's* own
interpreter, where ostler is not installed. So the planning happens here, ostler-side,
and the result is a plain JSON-safe dict handed across the process boundary as
`context["book_fixtures"]`. It carries `steps` (kind, command, cwd, timeout), the
declared `args`/`provides`/`secrets` names, and `needs` bindings with their `name=value`
args resolved to strings — but never a reference's *value*: `@node.key` and `$name`
substitution is the harness's own runtime job, not this module's.

**Secrets are NAMES only.** This dict is exactly what lands in the harness's context
JSON, so a fixture's `secrets:` bullet must never carry anything but the environment
variable name the harness resolves from its own environment at run time.

Each `steps` entry now carries its own `### id` anchor, and each `provides` entry is a
`{"key", "from", "read"}` dict rather than a bare key name: `from`/`read` are the
`provides:` entry's own declared properties (`registry.py`'s `provides` `BulletKey`),
carried through as plain strings so the harness can bind a fact to the step and path
that produced it instead of assuming the fixture's last step's whole stdout, keyed by
the fact's own name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ostler.markdown import extract_refs
from ostler.model import Graph, UINode
from ostler.qa import fixtures as fixtures_mod
from ostler.qa import runbook as runbook_mod
from ostler.qa.stack import STEP_TIMEOUT_S, boot_timeout


def _bullet_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def _declared_args(node: UINode) -> list[str]:
    names: list[str] = []
    for value in _bullet_values(node.meta.get("args")):
        names.extend(value.split())
    return names


def _property_text(value: object) -> str:
    if isinstance(value, list):
        return " ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip() if value is not None else ""


def _provides_from_step(raw: str) -> str:
    """The step `### id` a `from:` property names, read from its markdown link href."""
    links = extract_refs(raw).links
    if links:
        return links[0][1].lstrip("#")
    return raw.lstrip("#")


def _provides_read_path(raw: str) -> str:
    """The path portion of a `read:` property: an optional `json` format word, then a path

    in the grammar `ostler_qa.resolve_path` walks — the same one a `json_path` check uses,
    not a full jq pipeline (no `| length`, no filters beyond `[*]`/`[?(...)]`).
    """
    text = raw.strip()
    if text[:4].lower() == "json":
        text = text[4:].strip()
    return text.strip("`").strip()


def _declared_provides(node: UINode) -> list[dict[str, str]]:
    """Every fact a fixture's `provides:` declares, with its `from:`/`read:` extraction properties.

    `from:` names the step (by its `### id` anchor) whose stdout the fact is read from,
    defaulting to the fixture's last step when absent. `read:` names a JSON path within that
    step's stdout, defaulting to the fact's own key when absent — the shape a fixture written
    before this vocabulary existed already has, so an old book keeps behaving exactly as it did.
    """
    declared: list[dict[str, str]] = []
    for entry in node.entries.get("provides", []):
        head = entry.headline.partition("—")[0].split()
        if not head:
            continue
        key = head[0]
        from_raw = _property_text(entry.properties.get("from"))
        read_raw = _property_text(entry.properties.get("read"))
        declared.append({
            "key": key,
            "from": _provides_from_step(from_raw) if from_raw else "",
            "read": _provides_read_path(read_raw) if read_raw else "",
        })
    return declared


def _declared_secrets(node: UINode) -> list[str]:
    return [v.strip() for v in _bullet_values(node.meta.get("secrets")) if v.strip()]


def _needs_of(graph: Graph, node: UINode, by_name: dict[str, UINode]) -> list[dict[str, Any]]:
    """Each `needs:` child as `{"fixture": stem, "args": {name: value}}`.

    Parses the same shape `doctor._needs_binding` checks statically (a markdown link to
    the target fixture, then `name=value` tokens) — duplicated rather than imported,
    because `doctor` is a linting layer this module has no business depending on for the
    shape it hands the harness.
    """
    bindings: list[dict[str, Any]] = []
    for value in _bullet_values(node.meta.get("needs")):
        links = extract_refs(value).links
        if not links:
            continue
        text, href = links[0]
        target = graph.find_ui_node(graph.resolve_doc_ref(href, origin=node.path))
        if target is None:
            # A `needs:` link that does not resolve is a book defect, not something to run
            # the consumer without silently — the harness raises a fault when it reaches
            # this marker instead of skipping the dependency it names.
            bindings.append({"fixture": None, "unresolved": href, "args": {}})
            continue
        rest = value.replace(f"[{text}]({href})", "", 1).strip()
        stem = Path(target.id).stem
        parsed = fixtures_mod.parse_bullet(f"{stem} {rest}".strip())
        if not isinstance(parsed, fixtures_mod.FixtureRef):
            continue
        args = {tok.partition("=")[0]: tok.partition("=")[2] for tok in parsed.args if "=" in tok}
        resolved = by_name.get(stem, target)
        bindings.append({"fixture": Path(resolved.id).stem, "args": args})
    return bindings


def _steps_of(graph: Graph, node: UINode) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for step in runbook_mod.steps_of(graph, node):
        kind = runbook_mod.bullet_value(step.meta, "kind")
        command = runbook_mod.step_command(step, graph.root, ".")
        step_id = step.id.rpartition("#")[2]
        if command is None:
            # No `run:` bullet — the step would execute nothing. Carried as a marker
            # rather than dropped, so the harness raises a fault when it reaches this
            # step instead of running the fixture incomplete with no signal.
            steps.append({"kind": kind, "id": step_id, "missing_run": True})
            continue
        entry: dict[str, Any] = {
            "kind": kind,
            "id": step_id,
            "command": command["run"],
            "cwd": command["working-directory"],
            "timeout": boot_timeout(str(command.get("timeout", "")), default=STEP_TIMEOUT_S),
        }
        steps.append(entry)
    return steps


def resolved(graph: Graph) -> dict[str, dict[str, Any]]:
    """Every `fixture` node in the book, as the harness's `context["book_fixtures"]`.

    One entry per fixture, keyed by file stem — the name a `fixture:`/`needs:` bullet
    references it by.
    """
    nodes = graph.ui_nodes_of_type("fixture")
    by_name = {Path(n.id).stem: n for n in nodes}
    out: dict[str, dict[str, Any]] = {}
    for node in nodes:
        stem = Path(node.id).stem
        out[stem] = {
            "steps": _steps_of(graph, node),
            "args": _declared_args(node),
            "provides": _declared_provides(node),
            "needs": _needs_of(graph, node, by_name),
            "secrets": _declared_secrets(node),
        }
    return out
