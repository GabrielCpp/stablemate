---
type: concept
slug: dot-renderer
title: to_dot — render a workflow Graph to Graphviz DOT
---
# to_dot — render a workflow Graph to Graphviz DOT

Renders a validated [workflow](workflow.md) `Graph` (produced by
[load_workflow](load-workflow.md)) to a Graphviz DOT document, driving the
[`workhorse dot`](../workhorse.md#dot) command. The diagram is derived entirely from the `Graph`
model so it never drifts from the workflow it documents; styling is purely type-based (no
workflow-specific naming heuristics).

- code: `workhorse/workhorse/graph/dot.py::to_dot`
- verify: `workhorse/tests/test_dot.py`

## Contract

- **Input:**
  - `graph: Graph` — the workflow to render.
  - `pins: dict[str, str] | None` — maps a branch node's `path` to a fixed value; default none.
  - `name: str | None` — overrides the rendered `digraph` identifier; default none (falls back to
    `graph.name`).
  - `leaves: set[str] | None` — node ids to render as dead-ends; default none.
- **Output:** `str` — a complete `digraph { … }` DOT document, newline-terminated.
- **Determinism:** calling `to_dot` twice on the same `graph`/`pins`/`leaves` byte-for-byte matches
  (dict iteration preserves the YAML declaration order); all node declarations precede all edges.

## Algorithm

1. **Collapse pinned branches.** For every [`branch` node](workflow.md) whose `path` is a key in
   `pins`, resolve its single target by reusing the runtime branch evaluator
   (`workhorse/runner/branch.py::evaluate`) against a `WorkflowContext` seeded with `pins` — the
   same case/condition/default precedence the real run uses. A branch that can't resolve (the
   pinned value matches no case/condition and there's no default) is left uncollapsed and rendered
   in full rather than dropped.
2. **Compute reachability.** Breadth-first walk from `graph.start` over each node's outgoing edges:
   `agent`/`script`/`call`/`flow` nodes edge to `next`; a `branch` node edges to every `cases`
   value, every `conditions[].next`, and `default`, unless it was collapsed in step 1 (then just
   its one resolved edge); a node listed in `leaves` contributes no outgoing edges, so reachability
   stops there. `terminal`/`fail` nodes have none. Only reachable nodes/edges are emitted — this is
   what prunes the unpicked mode of a multi-mode graph (or the far side of a `leaves` cut).
3. **Emit node declarations**, in `graph.nodes` (YAML) order, restricted to the reachable set.
   Styling by node type:
   - `branch` → `shape=diamond`, `fillcolor=lightsalmon`.
   - `flow` → `shape=box3d`, `fillcolor=lightyellow`, two-line label (`id` / `flow: <name>`).
   - `terminal` → `fillcolor=lightgreen`, label suffixed `(terminal)`.
   - `fail` → `fillcolor=lightcoral`, label suffixed `(fail)`.
   - the **start node** → `fillcolor=lightgreen` (wins over type color), label prefixed `START`.
   - a plain `agent`/`script` node at the root with no special styling and a label equal to its id
     gets no explicit `[…]` declaration (it's emitted implicitly via its edges) — this keeps
     unstyled output minimal.
4. **Emit edges**, in `graph.nodes` order, restricted to reachable source *and* target. Parallel
   edges to the same target merge into one line, joining their labels with `|`. A `branch` edge is
   labeled with its case value, `"<op> <value>"` for a numeric condition, or `"default"`; unlabeled
   edges (agent/script/call/flow → `next`) render with no `[label=…]`.
5. **Render `flows:` clusters**, once per entry in `graph.flows` (skipped entirely if empty): a
   `subgraph cluster_<name>` containing that flow's own reachable nodes/edges (computed by
   recursing steps 2–4 on the flow's own `Graph`, with empty `pins`/`leaves` — a flow's phases are
   mode-agnostic), styled `style=dashed, color=gray55`, labeled `"flow: <name>"`. Every node id
   inside a cluster is prefixed `<flow>__` in the DOT namespace (so a flow reusing a parent node id
   never collides) while its visible label stays the bare id. Nested `flows:` (a flow that itself
   declares flows) recurse into cluster-in-cluster. After the clusters, draw a dashed
   `label="calls", constraint=false` edge from every reachable `flow` node in the outer graph into
   its cluster's start node; the `flow` node **also keeps its normal `next` edge** (drawn in step 4)
   so the parent's continuation after the phase stays visible.
6. Wrap the emitted declarations/edges/clusters in `digraph <name> { … }`, `<name>` = the sanitized
   `name` arg or `graph.name` (non-alphanumeric/underscore characters replaced with `_`; empty
   result falls back to `"workflow"`). All labels are escaped for a DOT double-quoted string
   (backslash and `"` escaped).

`pins`/`leaves` apply only to the root graph — each `flows:` cluster always renders its own full
internal graph.
