---
type: concept
slug: dashboard-tree-selection
title: Dashboard tree selection
---
# Dashboard tree selection

`buildTree`, `TreeDir`'s directory toggle, and the tree it produces are cited by three
concept nodes: [dashboard tree builder](dashboard-tree-builder.md), which documents the
function itself, and [dashboard tree flow selection](dashboard-tree-flow-selection.md) and
[dashboard tree input selection](dashboard-tree-input-selection.md), which each document one
orthogonal choice a caller makes before reaching it — which journey (Files vs Diff) and which
input shape (flat path list vs already-nested tree). None of the three is an alternative
implementation of another: there is exactly one `buildTree`, and the other two describe
decisions made *before* the call, not a second way to make it.

- rule: there is no ranking among the three — a reader needing the builder's contract wants [dashboard tree builder](dashboard-tree-builder.md); a reader choosing which journey to route through wants [dashboard tree flow selection](dashboard-tree-flow-selection.md); a reader choosing which input shape to hand it wants [dashboard tree input selection](dashboard-tree-input-selection.md).
