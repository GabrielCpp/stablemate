"""Render Python state machines to Graphviz DOT."""
from __future__ import annotations

import re
from collections.abc import Sequence

from workhorse.pyflow.graph import Edge, FlowGraph, StateNode

_HEADER = (
    "  rankdir=TB;\n"
    "  bgcolor=white;\n"
    "  compound=true;\n"
    "  newrank=true;\n"
    '  node [shape=box, style="rounded,filled", fillcolor=lightblue];\n'
    "  edge [color=darkblue, fontsize=10];\n"
)

_LOOK = {
    "continue": "",
    "await": "style=dashed, color=darkorange",
    "done": "color=darkgoldenrod",
}

_STEP_STYLE = {
    "call": "shape=box, fillcolor=white",
    "agent": "shape=note, fillcolor=lightyellow",
    "handoff": "shape=box, fillcolor=plum",
}

_LEGEND = [
    "  subgraph cluster_legend {",
    '    label="legend";',
    "    style=dashed; color=gray50; fontsize=11;",
    '    node [shape=plaintext, style="", fillcolor=white, fontsize=10];',
    '    legend_a [label=""]; legend_b [label=""];',
    '    legend_c [label=""]; legend_d [label=""];',
    '    legend_e [label=""]; legend_f [label=""];',
    '    legend_a -> legend_b [label="continue"];',
    '    legend_c -> legend_d [label="await: parked on an operator gate", '
    "style=dashed, color=darkorange];",
    '    legend_e -> legend_f [label="done: the flow ends", color=darkgoldenrod];',
    '    subgraph cluster_legend_state {',
    '      label="a state: what it runs, top to bottom";',
    '      style="rounded,filled"; fillcolor=lightblue; color=steelblue;',
    '      node [style="filled"];',
    f'      legend_call [label="a node call\\nits docstring", {_STEP_STYLE["call"]}];',
    f'      legend_agent [label="an agent turn: prompt.md\\nits title", {_STEP_STYLE["agent"]}];',
    f'      legend_handoff [label="handoff → a sub-flow\\nrun to its END, then back here", '
    f'{_STEP_STYLE["handoff"]}];',
    "      legend_call -> legend_agent -> legend_handoff [style=invis];",
    "    }",
    "  }",
]


def to_dot(graphs: Sequence[FlowGraph], name: str | None = None) -> str:
    """Render `graphs` to a Graphviz DOT document."""
    lines: list[str] = [f"digraph {_sanitize(name or 'workflow')} {{", _HEADER.rstrip("\n"), ""]
    labels = {graph.workflow: graph.label for graph in graphs}
    for index, graph in enumerate(graphs):
        if index:
            lines.append("")
        _emit_flow(graph, lines, prefix=f"f{index}__", labels=labels)
    lines.append("")
    lines.extend(_LEGEND)
    lines.append("}")
    return "\n".join(lines) + "\n"


def _emit_flow(
    graph: FlowGraph, lines: list[str], *, prefix: str, labels: dict[str, str]
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
        _emit_state(node, lines, prefix=prefix, unreachable=unreachable, labels=labels)
    if any(node.terminal for node in graph.states):
        lines.append(f'    {end_id} [label="END", shape=doublecircle, fillcolor=gold, width=0.4];')
    lines.append("")

    first = graph.state(graph.start)
    entry = _entry(prefix, first) if first is not None else _id(prefix, graph.start)
    clip = _clip(prefix, None, first).lstrip(", ")
    lines.append(f"    {start_id} -> {entry}{f' [{clip}]' if clip else ''};")
    for node in graph.states:
        for edges in _merged(node.edges):
            lines.append(f"    {_edge(prefix, node, edges, graph)};")
    lines.append("  }")


def _cluster(prefix: str, node: StateNode) -> str:
    return _sanitize(f"cluster_{prefix}{node.name}")


def _entry(prefix: str, node: StateNode) -> str:
    """The DOT node an edge into this state points at: its first bubble, else itself."""
    return f"{_id(prefix, node.name)}__0" if node.steps else _id(prefix, node.name)


def _exit(prefix: str, node: StateNode) -> str:
    """The DOT node an edge out of this state leaves from: its last bubble, else itself."""
    count = len(node.steps)
    return f"{_id(prefix, node.name)}__{count - 1}" if count else _id(prefix, node.name)


def _clip(prefix: str, tail: StateNode | None, head: StateNode | None) -> str:
    """`ltail`/`lhead` attributes so an edge stops at a boxed state's border."""
    attrs = []
    if tail is not None and tail.steps:
        attrs.append(f"ltail={_cluster(prefix, tail)}")
    if head is not None and head.steps:
        attrs.append(f"lhead={_cluster(prefix, head)}")
    return "".join(f", {a}" for a in attrs)


def _emit_state(
    node: StateNode,
    lines: list[str],
    *,
    prefix: str,
    unreachable: set[str],
    labels: dict[str, str],
) -> None:
    """A state: a rounded box holding one bubble per step, or a plain box when it runs nothing."""
    defect = node.opaque or node.name in unreachable
    fill = "lightcoral" if defect else "lightblue"
    steps = node.steps
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
        if step.kind == "handoff":
            parts = [f"handoff → {labels.get(step.name, step.name)}"]
        else:
            parts = [step.file, *([step.summary] if step.summary else [])]
        label = "\\n".join(_esc(part) for part in parts)
        lines.append(f'      {step_id} [label="{label}", {_STEP_STYLE[step.kind]}];')
    for tail, head in zip(ids, ids[1:], strict=False):
        lines.append(f"      {tail} -> {head} [style=invis];")
    lines.append("    }")


def _merged(edges: Sequence[Edge]) -> list[list[Edge]]:
    """The state's edges grouped by where they lead, so two returns to one place draw one arrow."""
    groups: dict[tuple[str, str], list[Edge]] = {}
    for edge in edges:
        key = ("done", "") if edge.kind == "done" else ("dynamic" if edge.dynamic else "state", edge.target)
        groups.setdefault(key, []).append(edge)
    return list(groups.values())


def _edge(prefix: str, node: StateNode, edges: Sequence[Edge], graph: FlowGraph) -> str:
    """One arrow for every transition from `node` to the same place."""
    edge = edges[0]
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
        target = _entry(prefix, into) if into is not None else _id(prefix, edge.target)
        head = ""

    attrs = []
    reasons = list(dict.fromkeys(e.reason for e in edges if e.reason))
    if reasons:
        attrs.append(f'label="{_esc(" / ".join(reasons))}"')
    params = list(dict.fromkeys(p for e in edges for p in e.params))
    if params:
        attrs.append(f'tooltip="{_esc(", ".join(params))}"')
    kind = "await" if any(e.kind == "await" for e in edges) else edge.kind
    if _LOOK[kind]:
        attrs.append(_LOOK[kind])
    clip = "" if into is node else _clip(prefix, node, into).lstrip(", ")
    if clip:
        attrs.append(clip)
    suffix = f" [{', '.join(attrs)}]" if attrs else ""
    return f"{head}{_exit(prefix, node)} -> {target}{suffix}"


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
