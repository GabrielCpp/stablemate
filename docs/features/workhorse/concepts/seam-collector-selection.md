---
type: concept
slug: seam-collector-selection
title: Seam collector selection
---
# Seam collector selection

A state graph's seam collectors are the accessors that read the engine seams
discovered by [`_scan`](pyflow-state-graph.md#algorithm): each `Step` is filtered by
`kind` (`call`, `agent`, or `handoff`) and projected to the strings the consumer wants.
They are not alternative implementations of one accessor — they target different seam
kinds at different levels, and the same seam may appear in more than one of them by
design.

- [`StateNode.calls`](pyflow-state-graph.md#statenodecalls) reads `kind == "call"` per
  state and yields blueprint node names in source order
  (`tuple[str, ...]`).
- [`FlowGraph.prompts()`](pyflow-state-graph.md#flowgraphprompts) reads
  `kind == "agent"` across every state and yields `(state, prompt)` pairs
  (`tuple[tuple[str, str], ...]`); `preflight` uses it to walk the workflow's prompt
  paths without naming any one state.
- [`StateNode.prompts`](pyflow-state-graph.md#statenodeprompts) reads `kind == "agent"`
  per state and yields literal prompt paths in source order (`tuple[str, ...]`); it is
  the per-state half of what `FlowGraph.prompts()` flattens.

The single test
`workhorse/tests/test_pyflow_graph.py::test_node_calls_and_prompt_paths_are_collected`
asserts them together because the underlying collection contract is one — every
literal `self.call(...)` ends up in the right state node's `calls`, and every literal
`self.agent(...)` ends up in the right state node's `prompts` **and** in the right slot
of the graph's flattened `(state, prompt)` sequence — not because the three accessors
are interchangeable. A reader needs node names from a single state reaches for
`StateNode.calls`; a reader needs every prompt a flow renders, with the state it lives
in, reaches for `FlowGraph.prompts()`.

- rule: select the collector whose level and seam kind match the question —
  `StateNode.calls` for node names per state, `StateNode.prompts` for prompt paths per
  state, `FlowGraph.prompts()` for the flattened `(state, prompt)` sequence the graph
  hands to `preflight`; none supersedes the others, and no collector replaces another
- tests: `workhorse/tests/test_pyflow_graph.py::test_node_calls_and_prompt_paths_are_collected`
