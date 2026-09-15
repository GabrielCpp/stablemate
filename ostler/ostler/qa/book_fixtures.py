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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ostler.markdown import extract_refs
from ostler.model import Graph, UINode
from ostler.qa import fixtures as fixtures_mod
from ostler.qa import runbook as runbook_mod


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


def _declared_provides(node: UINode) -> list[str]:
    """The fact names a fixture declares under `provides:` — see `doctor._fixture_declared_provides`."""
    keys: list[str] = []
    for value in _bullet_values(node.meta.get("provides")):
        head = value.partition("—")[0].split()
        if head:
            keys.append(head[0])
    return keys


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
        if isinstance(parsed, str):
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
        if command is None:
            # No `run:` bullet — the step would execute nothing. Carried as a marker
            # rather than dropped, so the harness raises a fault when it reaches this
            # step instead of running the fixture incomplete with no signal.
            steps.append({"kind": kind, "missing_run": True})
            continue
        entry: dict[str, Any] = {
            "kind": kind,
            "command": command["run"],
            "cwd": command["working-directory"],
        }
        if "timeout" in command:
            entry["timeout"] = command["timeout"]
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
