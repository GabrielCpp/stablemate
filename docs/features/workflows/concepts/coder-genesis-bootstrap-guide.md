---
type: concept
slug: coder-genesis-bootstrap-guide
title: Coder genesis bootstrap guide
---
# Coder genesis bootstrap guide

`Genesis` is one straight-line deterministic bootstrap workflow. Its fields are cumulative
inputs to that path: target classification determines whether repository initialization is
skipped, and service classification separately determines whether native initialization is
skipped. The workflow always continues through configuration, Farrier refresh, and validation.

Use [coder genesis bootstrap](coder-genesis-bootstrap.md) for the lifecycle, states, and field
contracts. Use [coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md)
to choose cumulative parameter values, including the `markers` fallback. Use [coder genesis
bootstrap scope](coder-genesis-bootstrap-scope.md) to understand why repository and service
state are independent. These are complementary views of the same `Genesis` implementation, not
alternatives and therefore have no preferred or deprecated implementation.

- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- rule: use the lifecycle concept for workflow behavior, input selection for parameter values, and scope for independent repository and service decisions; none replaces another
- detail: [coder genesis bootstrap concept selection](coder-genesis-bootstrap-concept-selection.md)
