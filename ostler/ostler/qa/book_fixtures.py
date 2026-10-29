"""Book-declared fixtures, walked into the shape the harness executes them from."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ostler.markdown import extract_refs
from ostler.model import Graph, UINode
from ostler.qa import fixture_browser
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
    return fixtures_mod.declared_names(_bullet_values(node.meta.get("args")))


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
    return fixtures_mod.declared_names(_bullet_values(node.meta.get("secrets")))


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


def on_stem(value: str) -> str:
    """The resource a step's `on:` names: the stem of its link, or the bare stem it is written as."""
    links = extract_refs(value).links
    target = links[0][1].partition("#")[0] if links else value.strip().strip("`")
    return Path(target).stem


def _request_of(text: str) -> dict[str, str]:
    """A step's `request:` as its method and path."""
    method, _, path = text.strip().partition(" ")
    return {"method": method.upper(), "path": path.strip()}


def step_entry(graph: Graph, step: UINode) -> dict[str, Any]:
    """One step as the harness runs it: a browser step's actions, a request on a resource, or a command."""
    kind = runbook_mod.bullet_value(step.meta, "kind")
    step_id = step.id.rpartition("#")[2]
    if fixture_browser.is_browser_step(step):
        performed = fixture_browser.browser_step(graph, step)
        if performed.problems:
            return {"kind": kind, "id": step_id, "unperformable": "; ".join(performed.problems)}
        return {"kind": kind, "id": step_id, "browser": performed.actions}
    on = runbook_mod.bullet_value(step.meta, "on")
    request = runbook_mod.bullet_value(step.meta, "request")
    timeout = boot_timeout(runbook_mod.bullet_value(step.meta, "timeout"), default=STEP_TIMEOUT_S)
    if request:
        body = runbook_mod.bullet_value(step.meta, "body")
        return {"kind": kind, "id": step_id, "on": on_stem(on), "request": _request_of(request),
                "body": body or None, "timeout": timeout}
    command = runbook_mod.step_command(step, runbook_mod.system_root(graph), ".")
    if command is None:
        return {"kind": kind, "id": step_id, "missing_run": True}
    entry: dict[str, Any] = {
        "kind": kind,
        "id": step_id,
        "command": command["run"],
        "timeout": boot_timeout(str(command.get("timeout", "")), default=STEP_TIMEOUT_S),
    }
    if on:
        entry["on"] = on_stem(on)
    if "cwd-frame" in command:
        entry["cwd-frame"] = command["cwd-frame"]
    else:
        entry["cwd"] = command["working-directory"]
    return entry


def _steps_of(graph: Graph, node: UINode) -> list[dict[str, Any]]:
    return [step_entry(graph, step) for step in runbook_mod.steps_of(graph, node)]


def _properties(node: UINode, key: str) -> dict[str, str]:
    """A nested bullet's `name: value` children."""
    found: dict[str, str] = {}
    for item in _bullet_values(node.meta.get(key)):
        name, sep, value = item.partition(":")
        if sep and name.strip():
            found[name.strip()] = value.strip().strip("`")
    return found


def resolved_resources(graph: Graph) -> dict[str, dict[str, Any]]:
    """Every `resource` node in the book, as the harness's `context["resources"]`: the reach, the secret names it needs (never their values), its probe and its observations."""
    out: dict[str, dict[str, Any]] = {}
    for node in graph.ui_nodes_of_type("resource"):
        steps = runbook_mod.steps_of(graph, node)
        probes = [step for step in steps if step.data.get("container") == "Probe"]
        credential = _properties(node, "credential")
        out[Path(node.id).stem] = {
            "page": node.id,
            "reach": runbook_mod.bullet_value(node.meta, "reach"),
            "base": runbook_mod.bullet_value(node.meta, "base"),
            "credential": {"header": credential.get("header", ""), "scheme": credential.get("scheme", ""),
                           "secret": credential.get("secret", "")} if credential else None,
            "binary": runbook_mod.bullet_value(node.meta, "binary"),
            "secrets": _declared_secrets(node),
            "install": runbook_mod.bullet_value(node.meta, "install"),
            "probe": step_entry(graph, probes[0]) if probes else None,
            "observations": {
                step.id.rpartition("#")[2]: step_entry(graph, step)
                for step in steps if step.data.get("container") == "Observations"},
        }
    return out


def resolved(graph: Graph) -> dict[str, dict[str, Any]]:
    """Every `fixture` node in the book, as the harness's `context["book_fixtures"]`."""
    nodes = graph.ui_nodes_of_type("fixture")
    by_name = {Path(n.id).stem: n for n in nodes}
    out: dict[str, dict[str, Any]] = {}
    for node in nodes:
        stem = Path(node.id).stem
        out[stem] = {
            "page": node.id,
            "steps": _steps_of(graph, node),
            "args": _declared_args(node),
            "provides": _declared_provides(node),
            "needs": _needs_of(graph, node, by_name),
            "secrets": _declared_secrets(node),
            "lifetime": "scenario" if _bullet_values(node.meta.get("lifetime")) == ["scenario"] else "lap",
        }
    return out
