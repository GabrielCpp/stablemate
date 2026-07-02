"""Render a workflow Graph to Graphviz DOT.

The diagram is derived entirely from the validated ``Graph`` (see loader.py /
nodes.py), so it never drifts from the workflow it documents. Styling is purely
type-based — branch/terminal/fail/flow get distinct shapes and colors; agent/script
nodes are plain boxes — with no workflow-specific naming heuristics.

A workflow whose entry is a mode branch (e.g. coder's ``decide_mode`` on the
``mode`` var) encodes several modes in ONE graph. Passing ``pins`` collapses any
branch whose ``path`` is a pinned key to its single resolved edge; the unreachable
mode is then pruned by the reachability walk. So ``pins={"mode": "epic"}`` yields
the epic-only view and ``{"mode": "story"}`` the story-only view.

A workflow's ``flows:`` sub-graphs (each invoked by a ``type: flow`` node and also
runnable standalone) are rendered as Graphviz ``subgraph cluster_*`` boxes — one per
flow — with a dashed "calls" edge from each invoking flow node into the cluster's
START node. The flow node also keeps its normal ``next`` edge, so the parent's
continuation after the phase stays visible. Cluster node ids are name-prefixed
(``<flow>__<id>``) so a flow that reuses a parent node id never collides in the
single DOT namespace; the visible label stays the bare id.
"""
from __future__ import annotations

import re
from collections import deque

from .nodes import AgentNode, BranchNode, CallNode, FlowNode, Graph, Node, ScriptNode, TerminalNode

_HEADER = (
    "  rankdir=TB;\n"
    "  bgcolor=white;\n"
    '  node [shape=box, style="rounded,filled", fillcolor=lightblue];\n'
    "  edge [color=darkblue, fontsize=10];\n"
)


def to_dot(
    graph: Graph,
    pins: dict[str, str] | None = None,
    name: str | None = None,
    leaves: set[str] | None = None,
) -> str:
    """Render ``graph`` to a Graphviz DOT document.

    ``pins`` maps a branch ``path`` to a fixed value; matching branches collapse to
    their single resolved edge (and the other-mode subgraph is pruned by
    reachability). ``leaves`` lists nodes to render as dead-ends — their outgoing
    edges are suppressed, so reachability stops there. This severs a cross-view
    bridge that isn't gated by a pinned branch (e.g. coder's ``replan_epic`` routes
    a story-mode run back into the epic queue; making it a leaf keeps the epic
    machinery out of the story diagram). ``name`` overrides the ``digraph``
    identifier (default: a sanitized ``graph.name``).

    Pins/leaves apply only to the root graph; each ``flows:`` cluster renders its own
    full internal graph (its phases are mode-agnostic).
    """
    pins = pins or {}
    leaves = leaves or set()

    # 1. Collapse pinned branches to their single resolved target. Reuse the runtime
    #    branch evaluator so case/condition/default precedence stays single-sourced.
    collapsed = _collapsed_branches(graph, pins)

    # 2. Reachability from the start node over the (possibly collapsed) edge set —
    #    this is what prunes the unpicked mode.
    reachable = _reachable(graph, collapsed, leaves)

    # 3. Emit nodes then edges in declaration order (dict preserves YAML order) for
    #    stable, diff-friendly output.
    digraph_name = _sanitize(name or graph.name)
    lines: list[str] = [f"digraph {digraph_name} {{", _HEADER.rstrip("\n"), ""]

    _emit_decls(graph, reachable, lines, prefix="", indent="  ")
    lines.append("")
    _emit_edges(graph, reachable, collapsed, leaves, lines, prefix="", indent="  ")

    # 4. Render each flows: sub-graph as a cluster, with a dashed "calls" edge from
    #    every reachable flow node that invokes it. Emitted after the root body, so a
    #    flow-free workflow's output is byte-for-byte unchanged.
    if graph.flows:
        lines.append("")
        _emit_flow_clusters(graph, reachable, lines, prefix="", indent="  ")

    lines.append("}")
    return "\n".join(lines) + "\n"


# ── Reachability / edges ────────────────────────────────────────────────────────

def _collapsed_branches(
    graph: Graph, pins: dict[str, str]
) -> dict[str, tuple[str, str]]:
    collapsed: dict[str, tuple[str, str]] = {}
    for node in graph.nodes.values():
        if isinstance(node, BranchNode) and node.path in pins:
            target = _resolve_pinned(node, pins)
            if target is not None:
                collapsed[node.id] = (target, str(pins[node.path]))
    return collapsed


def _reachable(
    graph: Graph, collapsed: dict[str, tuple[str, str]], leaves: set[str]
) -> set[str]:
    reachable: set[str] = {graph.start}
    queue: deque[str] = deque([graph.start])
    while queue:
        node = graph.nodes[queue.popleft()]
        for target, _ in _out_edges(node, collapsed, leaves):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    return reachable


def _out_edges(
    node: Node, collapsed: dict[str, tuple[str, str]], leaves: set[str]
) -> list[tuple[str, str | None]]:
    """Outgoing ``(target, label)`` edges for a node; label is None for unlabeled.

    A FlowNode's edge is its ``next`` (the parent's continuation AFTER the phase); the
    dashed "calls" edge into the flow's cluster is drawn separately by
    ``_emit_flow_clusters``."""
    if node.id in leaves:
        return []  # rendered as a dead-end; reachability stops here
    if node.id in collapsed:
        target, label = collapsed[node.id]
        return [(target, label)]
    if isinstance(node, (AgentNode, ScriptNode, CallNode, FlowNode)):
        return [(node.next, None)] if node.next else []
    if isinstance(node, BranchNode):
        edges: list[tuple[str, str | None]] = []
        for case_value, target in node.cases.items():
            edges.append((target, case_value))
        for cond in node.conditions:
            edges.append((cond.next, f"{cond.op} {cond.value}"))
        if node.default:
            edges.append((node.default, "default"))
        return edges
    return []  # terminal / fail


def _resolve_pinned(node: BranchNode, pins: dict[str, str]) -> str | None:
    """Single target a pinned branch routes to, or None if it can't be resolved."""
    from ..runner.branch import evaluate

    from .context import WorkflowContext

    try:
        target, _ = evaluate(node, WorkflowContext(initial=dict(pins)))
        return target
    except (RuntimeError, ValueError):
        # Pinned value matched no case/condition and the branch has no default;
        # fall back to rendering the branch in full rather than dropping it.
        return None


# ── Emission (shared by the root graph and each flow cluster) ────────────────────

def _emit_decls(
    graph: Graph, reachable: set[str], lines: list[str], *, prefix: str, indent: str
) -> None:
    """Emit styled node declarations for the reachable nodes of ``graph``. ``prefix``
    name-spaces the emitted DOT ids (``""`` for the root, ``<flow>__`` in a cluster);
    the visible label stays the bare node id."""
    for nid, node in graph.nodes.items():
        if nid not in reachable:
            continue
        decl = _node_decl(node, is_start=(nid == graph.start), ref=f"{prefix}{nid}")
        if decl is not None:
            lines.append(f"{indent}{decl}")


def _emit_edges(
    graph: Graph,
    reachable: set[str],
    collapsed: dict[str, tuple[str, str]],
    leaves: set[str],
    lines: list[str],
    *,
    prefix: str,
    indent: str,
) -> None:
    """Emit the reachable edges of ``graph`` (prefixed). Parallel edges to the same
    target merge into one, joining labels with '|'."""
    for nid, node in graph.nodes.items():
        if nid not in reachable:
            continue
        merged: dict[str, list[str]] = {}
        for target, label in _out_edges(node, collapsed, leaves):
            if target not in reachable:
                continue
            labels = merged.setdefault(target, [])
            if label and label not in labels:
                labels.append(label)
        for target, labels in merged.items():
            src, dst = f"{prefix}{nid}", f"{prefix}{target}"
            if labels:
                lines.append(f'{indent}{src} -> {dst} [label="{_esc("|".join(labels))}"];')
            else:
                lines.append(f"{indent}{src} -> {dst};")


def _emit_flow_clusters(
    graph: Graph, reachable: set[str], lines: list[str], *, prefix: str, indent: str
) -> None:
    """Render every ``flows:`` sub-graph of ``graph`` as a ``subgraph cluster_*`` and
    draw a dashed "calls" edge from each reachable flow node that invokes it. Recurses
    so a flow that itself declares ``flows:`` nests as a cluster-in-cluster."""
    inner = indent + "  "
    for fname, flow in graph.flows.items():
        cluster_id = _sanitize(f"{prefix}{fname}")
        node_prefix = f"{prefix}{fname}__"
        freach = _reachable(flow, {}, set())  # a flow renders its own full graph
        lines.append(f"{indent}subgraph cluster_{cluster_id} {{")
        lines.append(f'{inner}label="flow: {_esc(fname)}";')
        lines.append(f"{inner}style=dashed;")
        lines.append(f"{inner}color=gray55;")
        lines.append(f"{inner}fontsize=11;")
        _emit_decls(flow, freach, lines, prefix=node_prefix, indent=inner)
        _emit_edges(flow, freach, {}, set(), lines, prefix=node_prefix, indent=inner)
        # Nested flows (flow-in-flow) render as clusters within this one.
        if flow.flows:
            _emit_flow_clusters(flow, freach, lines, prefix=node_prefix, indent=inner)
        lines.append(f"{indent}}}")

    # "calls" edges from this graph's reachable flow nodes into the cluster START.
    for nid, node in graph.nodes.items():
        if nid not in reachable or not isinstance(node, FlowNode):
            continue
        flow = graph.flows.get(node.name)
        if flow is None:
            continue
        src = f"{prefix}{nid}"
        dst = f"{prefix}{node.name}__{flow.start}"
        lines.append(
            f'{indent}{src} -> {dst} [style=dashed, color=gray55, '
            f'label="calls", constraint=false];'
        )


def _node_decl(node: Node, *, is_start: bool, ref: str | None = None) -> str | None:
    """A styled node declaration for DOT id ``ref`` (default: the node id), or None
    when the node needs no explicit decl.

    Plain agent/script nodes at the root (default box, label == id) are emitted
    implicitly via their edges; only nodes with non-default styling, a shaped label,
    or a ``ref`` that differs from the id (cluster prefixing — the label must restate
    the bare id) get an explicit decl."""
    ref = ref or node.id
    shape: str | None = None
    fill: str | None = None
    label_lines = [node.id]

    if isinstance(node, BranchNode):
        shape = "diamond"
        fill = "lightsalmon"
    elif isinstance(node, FlowNode):
        shape = "box3d"
        fill = "lightyellow"
        label_lines = [node.id, f"flow: {node.name}"]
    elif isinstance(node, TerminalNode):
        if node.type == "terminal":
            fill = "lightgreen"
            label_lines = [node.id, "(terminal)"]
        else:  # fail
            fill = "lightcoral"
            label_lines = [node.id, "(fail)"]

    if is_start:
        fill = "lightgreen"  # start marker wins on color
        label_lines = ["START", *label_lines]

    label = "\\n".join(_esc(part) for part in label_lines)
    needs_label = label != ref

    if shape is None and fill is None and not needs_label:
        return None

    attrs: list[str] = []
    if shape:
        attrs.append(f"shape={shape}")
    if fill:
        attrs.append(f"fillcolor={fill}")
    attrs.append(f'label="{label}"')
    return f"{ref} [{', '.join(attrs)}];"


def _esc(text: str) -> str:
    """Escape a string for use inside a DOT double-quoted label."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _sanitize(name: str) -> str:
    """A valid DOT graph identifier derived from an arbitrary workflow name."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return cleaned or "workflow"
