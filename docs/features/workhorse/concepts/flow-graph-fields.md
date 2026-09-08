---
type: concept
slug: flow-graph-fields
title: FlowGraph fields
---
# FlowGraph fields

`FlowGraph` is one static description of a `Workflow` subclass. Its fields are complementary,
not competing representations: `workflow` identifies the class, `names` retains every registry
alias mapped to it, `start` selects the root for reachability, and `states` holds the statically
read live state nodes. The graph reader constructs all four together from the workflow class and
the registry names; no field substitutes for another or has a general preference.

- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph`
- rule: select the field matching the question: `workflow` for the class identity, `names` for registry aliases, `start` for reachability's root, and `states` for the discovered machine nodes; use `FlowGraph` for the complete record
