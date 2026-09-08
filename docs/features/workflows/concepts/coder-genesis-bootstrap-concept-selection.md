---
type: concept
slug: coder-genesis-bootstrap-concept-selection
title: Coder genesis bootstrap concept selection
---
# Coder genesis bootstrap concept selection

The concepts grounded in `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
describe different questions about the same bootstrap workflow. The source defines one
straight-line lifecycle with two independent skip-ahead decisions; its fields configure that
single path, and `markers` falls back to `marker` only when no explicit marker list is supplied.
It defines no alternative Genesis implementations and records no preferred or deprecated view.

Use [coder genesis bootstrap](coder-genesis-bootstrap.md) for the lifecycle, states, fields, and
methods. Use [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)
when choosing cumulative input values. Use [coder genesis bootstrap scope](coder-genesis-bootstrap-scope.md)
for the independent repository and service decisions. Use [coder genesis bootstrap guide](coder-genesis-bootstrap-guide.md)
for a short orientation across those views.

- rule: choose the lifecycle, input-selection, scope, or guide concept according to the question being answered; they are complementary views of one `Genesis` workflow, with no preferred or deprecated implementation
