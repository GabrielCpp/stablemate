"""Book-declared fixtures, walked into the shape the harness executes them from."""

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


def _provides_from_step(raw: str) -> str:
    """The step `### id` a `from:` property names, read from its markdown link href."""
    links = extract_refs(raw).links
    if links:
        return links[0][1].lstrip("#")
    return raw.lstrip("#")


def _provides_read_path(raw: str) -> str:
    """The path portion of a `read:` property: an optional `json` format word, then a path"""
    text = raw.strip()
    if text[:4].lower() == "json":
        text = text[4:].strip()
    return text.strip("`").strip()


def _declared_provides(node: UINode) -> list[dict[str, str]]:
    """Every fact a fixture's `provides:` declares, with the property that says where it comes from."""
    declared: list[dict[str, str]] = []
    for entry in node.entries.get("provides", []):
        head = entry.headline.partition("—")[0].split()
        if not head:
            continue
        key = head[0]
        from_raw = entry.property_text("from")
        read_raw = entry.property_text("read")
        is_raw = entry.property_text("is")
        declared.append({
            "key": key,
            "from": _provides_from_step(from_raw) if from_raw else "",
            "read": _provides_read_path(read_raw) if read_raw else "",
            "is": is_raw.strip() if is_raw else "",
        })
    return declared


def _declared_secrets(node: UINode) -> list[str]:
    return [v.strip() for v in _bullet_values(node.meta.get("secrets")) if v.strip()]


def _needs_of(graph: Graph, node: UINode, by_name: dict[str, UINode]) -> list[dict[str, Any]]:
    """Each `needs:` child as `{"fixture": stem, "args": {name: value}}`."""
    bindings: list[dict[str, Any]] = []
    for value in _bullet_values(node.meta.get("needs")):
        links = extract_refs(value).links
        if not links:
            continue
        text, href = links[0]
        target = graph.find_ui_node(graph.resolve_doc_ref(href, origin=node.path))
        if target is None:
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
        command = runbook_mod.step_command(step, runbook_mod.system_root(graph), ".")
        step_id = step.id.rpartition("#")[2]
        if command is None:
            steps.append({"kind": kind, "id": step_id, "missing_run": True})
            continue
        entry: dict[str, Any] = {
            "kind": kind,
            "id": step_id,
            "command": command["run"],
            "timeout": boot_timeout(str(command.get("timeout", "")), default=STEP_TIMEOUT_S),
        }
        if "cwd-frame" in command:
            entry["cwd-frame"] = command["cwd-frame"]
        else:
            entry["cwd"] = command["working-directory"]
        steps.append(entry)
    return steps


def resolved(graph: Graph) -> dict[str, dict[str, Any]]:
    """Every `fixture` node in the book, as the harness's `context["book_fixtures"]`."""
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
