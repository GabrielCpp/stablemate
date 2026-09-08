---
type: concept
slug: edge-transition-record
title: Edge transition record
---
# Edge transition record

An `Edge` is one statically discovered transition. Its fields are complementary observations of
that transition, not alternative representations: use the field that answers the question at
hand, and read the record as a whole when evaluating reachability or rendering the graph.

- code: `workhorse/workhorse/pyflow/graph.py::Edge`
- rule: Select `target` for the destination, `kind` for whether it continues, awaits, or ends,
  `params` and `reason` for its label, and `dynamic` or `dangling` for static-analysis limits.
  No field supersedes another; `target` is empty only for a `done` edge.
- tests: [state graph tests](../../../../workhorse/tests/test_pyflow_graph.py)
