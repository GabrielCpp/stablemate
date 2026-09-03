"""Render Python state machines to Graphviz DOT.

The sibling of `graph/dot.py`, and deliberately not an extension of it: that one walks
a validated `Graph` of declared nodes, this one walks a `FlowGraph` derived from source
(see `pyflow/graph.py`). Sharing a renderer would have meant one function branching on
which engine it was serving, so the styling vocabulary is shared by eye — same header,
same escaping rules, same "START is green, END is gold, red is a defect" reading — and
the code is not.

A state is never drawn as terminal. `Done` is one transition out of a state, so it is
drawn as one: an edge into the flow's single END sink. A green box with an arrow leaving
it was a contradiction on the page, and in a sub-flow it was also a lie — `Done` there
returns to the parent's `handoff`, which is what the END sink now says.

A state is drawn as what it runs. Its body is a chain of seams — a node call, an
agent turn, another call — so the state is a rounded box holding one bubble per step,
top to bottom in source order, each captioned with what its author already wrote about
it: the first line of the node's docstring, or the prompt's title. A state that runs
nothing is the plain rounded box it always was. Transitions leave the last bubble and
enter the first, clipped to the state's border (`compound=true`), so the reader follows
the machine between boxes and the work inside them without a second diagram.

Each flow becomes a `subgraph cluster_*`, so a distribution with several flows renders
as one document; node ids are flow-prefixed so two flows sharing a state name never
collide in the single DOT namespace, while the visible label stays the bare name. A
handoff to a flow in the same document is drawn as a dashed edge into that flow's START,
and that flow's END points back at the state that handed off. Those two edges are
written after every cluster, at the top level: Graphviz files a node under the first
subgraph that mentions it, so a cross edge written inside the parent's cluster would
drag the child's START into the parent's box, and the parent would read as a flow with
two starts.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from workhorse.pyflow.graph import Edge, FlowGraph, StateNode, Step

_HEADER = (
    "  rankdir=TB;\n"
    "  bgcolor=white;\n"
    "  compound=true;\n"
    # Rank clusters as one graph: the old ranker trips over clipped edges between boxes.
    "  newrank=true;\n"
    '  node [shape=box, style="rounded,filled", fillcolor=lightblue];\n'
    "  edge [color=darkblue, fontsize=10];\n"
)

#: How a step bubble looks, by kind: a node call is a plain white box, an agent turn is
#: a note in the prompt's own colour, a handoff to a flow outside the document is gray.
_STEP_STYLE = {
    "call": "shape=box, fillcolor=white",
    "agent": "shape=note, fillcolor=lightyellow",
    "handoff": "shape=box, fillcolor=lightgray",
}

#: What each arrow style means, drawn once on the page so the reader does not have to
#: know the engine's vocabulary: a plain step, a step behind an operator gate, the end
#: of the flow, and a handoff into a sub-flow and back.
_LEGEND = [
    "  subgraph cluster_legend {",
    '    label="legend";',
    "    style=dashed; color=gray50; fontsize=11;",
    '    node [shape=plaintext, style="", fillcolor=white, fontsize=10];',
    '    legend_a [label=""]; legend_b [label=""];',
    '    legend_c [label=""]; legend_d [label=""];',
    '    legend_e [label=""]; legend_f [label=""];',
    '    legend_g [label=""]; legend_h [label=""];',
    '    legend_a -> legend_b [label="continue"];',
    '    legend_c -> legend_d [label="await: parked on an operator gate", '
    "style=dashed, color=darkorange];",
    '    legend_e -> legend_f [label="done: the flow ends", color=darkgoldenrod];',
    '    legend_g -> legend_h [label="handoff to a sub-flow, and back", '
    "style=dashed, color=gray40];",
    '    subgraph cluster_legend_state {',
    '      label="a state: what it runs, top to bottom";',
    '      style="rounded,filled"; fillcolor=lightblue; color=steelblue;',
    '      node [style="filled"];',
    f'      legend_call [label="a node call\\nits docstring", {_STEP_STYLE["call"]}];',
    f'      legend_agent [label="an agent turn: prompt.md\\nits title", {_STEP_STYLE["agent"]}];',
    "      legend_call -> legend_agent [color=gray40, arrowsize=0.6];",
    "    }",
    "  }",
]


def to_dot(graphs: Sequence[FlowGraph], name: str | None = None) -> str:
    """Render `graphs` to a Graphviz DOT document."""
    lines: list[str] = [f"digraph {_sanitize(name or 'workflow')} {{", _HEADER.rstrip("\n"), ""]
    prefixes = {graph.workflow: f"f{index}__" for index, graph in enumerate(graphs)}
    callers = _callers(graphs, prefixes)
    crossing: list[str] = []
    for index, graph in enumerate(graphs):
        if index:
            lines.append("")
        _emit_flow(
            graph, lines, crossing, prefix=f"f{index}__", prefixes=prefixes, callers=callers
        )
    if crossing:
        lines.append("")
        lines.extend(f"  {edge};" for edge in crossing)
    lines.append("")
    lines.extend(_LEGEND)
    lines.append("}")
    return "\n".join(lines) + "\n"


def _callers(
    graphs: Sequence[FlowGraph], prefixes: dict[str, str]
) -> dict[str, list[tuple[str, str]]]:
    """Child class name → `(state name, return edge)` for every state that hands off to it.

    The return edge is the DOT text after `END ->`: the caller's entry bubble, clipped
    to its box when it has one.
    """
    callers: dict[str, list[tuple[str, str]]] = {}
    for graph in graphs:
        prefix = prefixes[graph.workflow]
        for node in graph.states:
            for child in node.handoffs:
                if child in prefixes:
                    edge = (
                        f"{_entry(prefix, node, prefixes)} "
                        f"[style=dashed, color=gray40{_clip(prefix, None, node, prefixes)}]"
                    )
                    callers.setdefault(child, []).append((node.name, edge))
    return callers


def _emit_flow(
    graph: FlowGraph,
    lines: list[str],
    crossing: list[str],
    *,
    prefix: str,
    prefixes: dict[str, str],
    callers: dict[str, list[tuple[str, str]]],
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
    # One START and one END per flow, and never the same colour: where a run comes in
    # and where it leaves are the two things a reader looks for first.

    for node in graph.states:
        _emit_state(node, lines, prefix=prefix, unreachable=unreachable, prefixes=prefixes)
    # A sub-flow's `Done` is not the end of the run: the driver returns to the
    # parent's `handoff`, and the sink says so rather than looking like a stop.
    back = callers.get(graph.workflow, [])
    if any(node.terminal for node in graph.states):
        # The return is written beside the circle (`xlabel`), not inside it, so the
        # sink stays the same small ring as START instead of growing to fit a sentence.
        note = ""
        if back:
            names = ", ".join(name for name, _ in back)
            note = f', xlabel="→ back to {_esc(names)}"'
        lines.append(
            f'    {end_id} [label="END", shape=doublecircle, fillcolor=gold, width=0.4{note}];'
        )
    lines.append("")

    first = graph.state(graph.start)
    entry = _entry(prefix, first, prefixes) if first is not None else _id(prefix, graph.start)
    clip = _clip(prefix, None, first, prefixes).lstrip(", ")
    lines.append(f"    {start_id} -> {entry}{f' [{clip}]' if clip else ''};")
    for node in graph.states:
        for edge in node.edges:
            lines.append(f"    {_edge(prefix, node, edge, graph, prefixes)};")
        for child in node.handoffs:
            if child in prefixes:
                crossing.append(
                    f"{_exit(prefix, node, prefixes)} -> {prefixes[child]}__start "
                    f'[label="handoff", style=dashed, color=gray40{_clip(prefix, node, None, prefixes)}]'
                )
    crossing.extend(f"{end_id} -> {edge}" for _, edge in back)
    lines.append("  }")


def _steps(node: StateNode, prefixes: dict[str, str]) -> list[Step]:
    """What the state's box holds: its steps, then any handoff not drawn as an edge."""
    foreign = [h for h in node.handoffs if h not in prefixes]
    return [*node.steps, *(Step("handoff", h) for h in foreign)]


def _cluster(prefix: str, node: StateNode) -> str:
    return _sanitize(f"cluster_{prefix}{node.name}")


def _entry(prefix: str, node: StateNode, prefixes: dict[str, str]) -> str:
    """The DOT node an edge into this state points at: its first bubble, else itself."""
    return f"{_id(prefix, node.name)}__0" if _steps(node, prefixes) else _id(prefix, node.name)


def _exit(prefix: str, node: StateNode, prefixes: dict[str, str]) -> str:
    """The DOT node an edge out of this state leaves from: its last bubble, else itself."""
    count = len(_steps(node, prefixes))
    return f"{_id(prefix, node.name)}__{count - 1}" if count else _id(prefix, node.name)


def _clip(
    prefix: str, tail: StateNode | None, head: StateNode | None, prefixes: dict[str, str]
) -> str:
    """`ltail`/`lhead` attributes so an edge stops at a boxed state's border."""
    attrs = []
    if tail is not None and _steps(tail, prefixes):
        attrs.append(f"ltail={_cluster(prefix, tail)}")
    if head is not None and _steps(head, prefixes):
        attrs.append(f"lhead={_cluster(prefix, head)}")
    return "".join(f", {a}" for a in attrs)


def _emit_state(
    node: StateNode,
    lines: list[str],
    *,
    prefix: str,
    unreachable: set[str],
    prefixes: dict[str, str],
) -> None:
    """A state: a rounded box holding one bubble per step, or a plain box when it runs
    nothing.

    Where the machine stops is a reader's first question, and the answer is the END
    sink and the edges into it — never a colour on a state, because a state that can
    end on one branch still continues on another. Unreachable and opaque states are
    red because they are defects the same walk already found. A handoff to a flow in
    the document is drawn as an edge instead of a bubble.
    """
    defect = node.opaque or node.name in unreachable
    fill = "lightcoral" if defect else "lightblue"
    steps = _steps(node, prefixes)
    if not steps:
        attrs = [f'label="{_esc(node.name)}"']
        if defect:
            attrs.append(f"fillcolor={fill}")
        if node.opaque:
            attrs.append('style="rounded,filled,dashed"')
        lines.append(f"    {_id(prefix, node.name)} [{', '.join(attrs)}];")
        return
    lines.append(f"    subgraph {_cluster(prefix, node)} {{")
    lines.append(f'      label="{_esc(node.name)}"; fontsize=12;')
    lines.append(f'      style="rounded,filled"; fillcolor={fill}; color=steelblue;')
    lines.append('      node [style="filled", fontsize=10];')
    ids = [f"{_id(prefix, node.name)}__{i}" for i in range(len(steps))]
    for step_id, step in zip(ids, steps, strict=True):
        # `\n` (the two characters) is DOT's line break, so it is joined in AFTER each
        # part is escaped — escaping the joined string would turn the break into text.
        title = f"handoff {step.name}" if step.kind == "handoff" else step.file
        parts = [title, *([step.summary] if step.summary else [])]
        label = "\\n".join(_esc(part) for part in parts)
        lines.append(f'      {step_id} [label="{label}", {_STEP_STYLE[step.kind]}];')
    for tail, head in zip(ids, ids[1:], strict=False):
        lines.append(f"      {tail} -> {head} [color=gray40, arrowsize=0.6];")
    lines.append("    }")


def _edge(
    prefix: str, node: StateNode, edge: Edge, graph: FlowGraph, prefixes: dict[str, str]
) -> str:
    """One transition. Dynamic and dangling targets get their own sink, not a state."""
    into: StateNode | None = None
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
        into = graph.state(edge.target)
        target = _entry(prefix, into, prefixes) if into is not None else _id(prefix, edge.target)
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
        attrs.append("color=darkgoldenrod")
    # A state looping on itself runs its chain again: the edge goes from the last
    # bubble back to the first, inside the box, and clipping it to the box's own border
    # would only make Graphviz complain that both ends are inside it.
    clip = "" if into is node else _clip(prefix, node, into, prefixes).lstrip(", ")
    if clip:
        attrs.append(clip)
    suffix = f" [{', '.join(attrs)}]" if attrs else ""
    return f"{head}{_exit(prefix, node, prefixes)} -> {target}{suffix}"


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
