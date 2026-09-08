---
type: concept
slug: epic-split-resolve-documentation-scope
title: Epic split resolve documentation scope
---
# Epic split resolve documentation scope

`workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve` is the sole
implementation of the epic-split resolution state. It asks an unbounded-timeout resolver agent to
diagnose an unresolved split decision, then parks the flow at the operator context. There is no
alternate implementation or source-defined ranking between the two documentation nodes that ground
themselves in it.

Use [Author epic split subflow](author-epic-split-subflow.md#resolve) for `resolve`'s control-flow
contract — which prompt it runs, what it returns, and the `Await` it parks the flow on. Use
[Epic split resolve prompt args](epic-split-resolve-prompt-args.md) for the six template arguments
`resolve` assembles for that prompt call and where each one comes from. Both describe the same
method and must remain consistent rather than being chosen as competing implementations.

- rule: use Author epic split subflow for `resolve`'s control-flow contract and Epic split resolve
  prompt args for the prompt-argument assembly it performs; neither is a different implementation
  or a deprecated alternative.
