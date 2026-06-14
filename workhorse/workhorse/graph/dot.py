"""Render a workflow Graph to Graphviz DOT.

The diagram is derived entirely from the validated ``Graph`` (see loader.py /
nodes.py), so it never drifts from the workflow it documents. Styling is purely
type-based — branch/terminal/fail get distinct shapes and colors; agent/script
nodes are plain boxes — with no workflow-specific naming heuristics.

A workflow whose entry is a mode branch (e.g. coder's ``decide_mode`` on the
``mode`` var) encodes several modes in ONE graph. Passing ``pins`` collapses any
branch whose ``path`` is a pinned key to its single resolved edge; the unreachable
mode is then pruned by the reachability walk. So ``pins={"mode": "epic"}`` yields
the epic-only view and ``{"mode": "story"}`` the story-only view.
"""
from __future__ import annotations

import re
from collections import deque

from .nodes import AgentNode, BranchNode, Graph, Node, ScriptNode, TerminalNode

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
    """
    pins = pins or {}
    leaves = leaves or set()

    # 1. Collapse pinned branches to their single resolved target. Reuse the runtime
    #    branch evaluator so case/condition/default precedence stays single-sourced;
    #    import it lazily to keep the graph package free of a module-level dependency
    #    on the runner layer (which itself imports graph).
    collapsed: dict[str, tuple[str, str]] = {}
    for node in graph.nodes.values():
        if isinstance(node, BranchNode) and node.path in pins:
            target = _resolve_pinned(node, pins)
            if target is not None:
                collapsed[node.id] = (target, str(pins[node.path]))

    # 2. Reachability from the start node over the (possibly collapsed) edge set —
    #    this is what prunes the unpicked mode.
    reachable: set[str] = set()
    queue: deque[str] = deque([graph.start])
    reachable.add(graph.start)
    while queue:
        node = graph.nodes[queue.popleft()]
        for target, _ in _out_edges(node, collapsed, leaves):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)

    # 3. Emit nodes then edges in declaration order (dict preserves YAML order) for
    #    stable, diff-friendly output.
    digraph_name = _sanitize(name or graph.name)
    lines: list[str] = [f"digraph {digraph_name} {{", _HEADER.rstrip("\n"), ""]

    for nid, node in graph.nodes.items():
        if nid not in reachable:
            continue
        decl = _node_decl(node, is_start=(nid == graph.start))
        if decl is not None:
            lines.append(f"  {decl}")
    lines.append("")

    for nid, node in graph.nodes.items():
        if nid not in reachable:
            continue
        # Merge parallel edges to the same target into one, joining their labels with
        # '|' (e.g. a branch whose `default` falls through to a named case's node →
        # "failed|default" rather than two duplicate arrows). Preserves first-seen
        # target order and de-dupes identical labels.
        merged: dict[str, list[str]] = {}
        for target, label in _out_edges(node, collapsed, leaves):
            if target not in reachable:
                continue
            labels = merged.setdefault(target, [])
            if label and label not in labels:
                labels.append(label)
        for target, labels in merged.items():
            if labels:
                lines.append(f'  {nid} -> {target} [label="{_esc("|".join(labels))}"];')
            else:
                lines.append(f"  {nid} -> {target};")

    lines.append("}")
    return "\n".join(lines) + "\n"


def _out_edges(
    node: Node, collapsed: dict[str, tuple[str, str]], leaves: set[str]
) -> list[tuple[str, str | None]]:
    """Outgoing ``(target, label)`` edges for a node; label is None for unlabeled."""
    if node.id in leaves:
        return []  # rendered as a dead-end; reachability stops here
    if node.id in collapsed:
        target, label = collapsed[node.id]
        return [(target, label)]
    if isinstance(node, (AgentNode, ScriptNode)):
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


def _node_decl(node: Node, *, is_start: bool) -> str | None:
    """A styled node declaration, or None when the node needs no explicit decl.

    Plain agent/script nodes (default box, label == id) are emitted implicitly via
    their edges; only nodes with non-default styling or a shaped label are declared.
    """
    shape: str | None = None
    fill: str | None = None
    label_lines = [node.id]

    if isinstance(node, BranchNode):
        shape = "diamond"
        fill = "lightsalmon"
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
    needs_label = label != node.id

    if shape is None and fill is None and not needs_label:
        return None

    attrs: list[str] = []
    if shape:
        attrs.append(f"shape={shape}")
    if fill:
        attrs.append(f"fillcolor={fill}")
    attrs.append(f'label="{label}"')
    return f"{node.id} [{', '.join(attrs)}];"


def _esc(text: str) -> str:
    """Escape a string for use inside a DOT double-quoted label."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _sanitize(name: str) -> str:
    """A valid DOT graph identifier derived from an arbitrary workflow name."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return cleaned or "workflow"
