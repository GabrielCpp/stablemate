"""Render Python state machines to Graphviz DOT.

The sibling of `graph/dot.py`, and deliberately not an extension of it: that one walks
a validated `Graph` of declared nodes, this one walks a `FlowGraph` derived from source
(see `pyflow/graph.py`). Sharing a renderer would have meant one function branching on
which engine it was serving, so the styling vocabulary is shared by eye — same header,
same escaping rules, same "START and END are the only green things" reading — and the
code is not.

A state is never drawn as terminal. `Done` is one transition out of a state, so it is
drawn as one: an edge into the flow's single END sink. A green box with an arrow leaving
it was a contradiction on the page, and in a sub-flow it was also a lie — `Done` there
returns to the parent's `handoff`, which is what the END sink now says.

Each flow becomes a `subgraph cluster_*`, so a distribution with several flows renders
as one document; node ids are flow-prefixed so two flows sharing a state name never
collide in the single DOT namespace, while the visible label stays the bare name. A
handoff to a flow in the same document is drawn as a dashed edge into that flow's START,
and that flow's END points back at the state that handed off.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from workhorse.pyflow.graph import Edge, FlowGraph, StateNode

_HEADER = (
    "  rankdir=TB;\n"
    "  bgcolor=white;\n"
    '  node [shape=box, style="rounded,filled", fillcolor=lightblue];\n'
    "  edge [color=darkblue, fontsize=10];\n"
)

#: How many `self.call` / `self.agent` names a state's label lists before eliding.
_MAX_DETAIL = 4


def to_dot(graphs: Sequence[FlowGraph], name: str | None = None) -> str:
    """Render `graphs` to a Graphviz DOT document."""
    lines: list[str] = [f"digraph {_sanitize(name or 'workflow')} {{", _HEADER.rstrip("\n"), ""]
    prefixes = {graph.workflow: f"f{index}__" for index, graph in enumerate(graphs)}
    callers = _callers(graphs, prefixes)
    for index, graph in enumerate(graphs):
        if index:
            lines.append("")
        _emit_flow(graph, lines, prefix=f"f{index}__", prefixes=prefixes, callers=callers)
    lines.append("}")
    return "\n".join(lines) + "\n"


def _callers(graphs: Sequence[FlowGraph], prefixes: dict[str, str]) -> dict[str, list[str]]:
    """Child class name → the prefixed ids of every state that hands off to it."""
    callers: dict[str, list[str]] = {}
    for graph in graphs:
        prefix = prefixes[graph.workflow]
        for node in graph.states:
            for child in node.handoffs:
                if child in prefixes:
                    callers.setdefault(child, []).append(_id(prefix, node.name))
    return callers


def _emit_flow(
    graph: FlowGraph,
    lines: list[str],
    *,
    prefix: str,
    prefixes: dict[str, str],
    callers: dict[str, list[str]],
) -> None:
    cluster = _sanitize(f"cluster_{graph.label}_{prefix}")
    lines.append(f"  subgraph {cluster} {{")
    lines.append(f'    label="{_esc(graph.label)}";')
    lines.append("    style=dashed; color=gray50; fontsize=11;")
    lines.append("")

    start_id = f"{prefix}__start"
    end_id = f"{prefix}__end"
    unreachable = set(graph.unreachable())
    lines.append(f'    {start_id} [label="START", shape=circle, fillcolor=lightgreen, width=0.4];')
    for node in graph.states:
        lines.append(f"    {_id(prefix, node.name)} {_decl(node, unreachable, prefixes)};")
    # A sub-flow's `Done` is not the end of the run: the driver returns to the
    # parent's `handoff`, and the sink says so rather than looking like a stop.
    back = callers.get(graph.workflow, [])
    if any(node.terminal for node in graph.states):
        label = "END"
        if back:
            label += " → back to " + ", ".join(b.split("__", 1)[-1] for b in back)
        lines.append(
            f'    {end_id} [label="{_esc(label)}", shape=doublecircle, '
            "fillcolor=lightgreen, width=0.4];"
        )
    lines.append("")

    lines.append(f"    {start_id} -> {_id(prefix, graph.start)};")
    for node in graph.states:
        for edge in node.edges:
            lines.append(f"    {_edge(prefix, node, edge)};")
        for child in node.handoffs:
            if child in prefixes:
                lines.append(
                    f"    {_id(prefix, node.name)} -> {prefixes[child]}__start "
                    '[label="handoff", style=dashed, color=gray40];'
                )
    for caller in back:
        lines.append(f"    {end_id} -> {caller} [style=dashed, color=gray40];")
    lines.append("  }")


def _decl(node: StateNode, unreachable: set[str], prefixes: dict[str, str]) -> str:
    """A state's declaration: its name, what it runs, and how it stands out.

    Where the machine stops is a reader's first question, and the answer is the END
    sink and the edges into it — never a colour on a state, because a state that can
    end on one branch still continues on another. Unreachable and opaque states are
    red because they are defects the same walk already found. A handoff to a flow in
    the document is drawn as an edge instead of named here.
    """
    parts = [node.name]
    if node.calls:
        parts.append("call " + _elide(node.calls))
    if node.prompts:
        parts.append("agent " + _elide([p.rsplit("/", 1)[-1] for p in node.prompts]))
    foreign = [h for h in node.handoffs if h not in prefixes]
    if foreign:
        parts.append("handoff " + _elide(foreign))

    # `\n` (the two characters) is DOT's line break, so it is joined in AFTER each
    # part is escaped — escaping the joined string would turn the break into text.
    label = "\\n".join(_esc(part) for part in parts)
    attrs = [f'label="{label}"']
    if node.opaque:
        attrs.append("fillcolor=lightcoral")
        attrs.append('style="rounded,filled,dashed"')
    elif node.name in unreachable:
        attrs.append("fillcolor=lightcoral")
    return f"[{', '.join(attrs)}]"


def _edge(prefix: str, node: StateNode, edge: Edge) -> str:
    """One transition. Dynamic and dangling targets get their own sink, not a state."""
    if edge.kind == "done":
        target = f"{prefix}__end"
        head = ""
    elif edge.dynamic:
        target = f"{_id(prefix, node.name)}__dyn"
        head = f'{target} [label="{_esc(edge.target)}", shape=note, fillcolor=lightgray]; '
    elif edge.dangling:
        target = _id(prefix, edge.target)
        head = f'{target} [label="{_esc(edge.target)}?", fillcolor=lightcoral]; '
    else:
        target = _id(prefix, edge.target)
        head = ""

    # The reason says why the edge is taken; the parameter list says only what it
    # carries. When the author wrote the former, the latter is plumbing and is dropped.
    attrs = []
    if edge.reason:
        attrs.append(f'label="{_esc(edge.reason)}"')
    elif edge.params:
        attrs.append(f'label="{_esc(", ".join(edge.params))}"')
    if edge.kind == "await":
        attrs.append("style=dashed")
        attrs.append("color=darkorange")
    elif edge.kind == "done":
        attrs.append("color=darkgreen")
    suffix = f" [{', '.join(attrs)}]" if attrs else ""
    return f"{head}{_id(prefix, node.name)} -> {target}{suffix}"


def _elide(items: Sequence[str]) -> str:
    shown = list(items[:_MAX_DETAIL])
    if len(items) > _MAX_DETAIL:
        shown.append("…")
    return ", ".join(shown)


def _id(prefix: str, name: str) -> str:
    return _sanitize(f"{prefix}{name}")


def _esc(text: str) -> str:
    """Escape a string for use inside a DOT double-quoted label."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _sanitize(name: str) -> str:
    """A valid DOT identifier derived from an arbitrary flow or state name."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return cleaned or "workflow"


__all__ = ["to_dot"]
