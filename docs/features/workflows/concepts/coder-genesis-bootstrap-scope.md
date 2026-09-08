---
type: concept
slug: coder-genesis-bootstrap-scope
title: Coder genesis bootstrap scope
---
# Coder genesis bootstrap scope

`Genesis` is one deterministic bootstrap workflow, entered before the main coder loop and
responsible for establishing the repository, service, Farrier, and validation preconditions.
Its fields are cumulative inputs to that workflow rather than alternate bootstrap
implementations.

Use [coder genesis bootstrap](coder-genesis-bootstrap.md) to understand the complete lifecycle,
its states, and the conditions that skip repository or service initialization. Use
[coder genesis bootstrap input selection](coder-genesis-bootstrap-input-selection.md) when
choosing values for those fields. Repository state and service state remain independent so an
existing repository can still gain a new service; an empty `markers` input falls back to
`marker`, while a supplied `markers` input is the complete marker list.

- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- rule: use the bootstrap concept for the deterministic lifecycle and the input-selection concept for cumulative field values; neither is an alternative implementation
- detail: [coder genesis bootstrap concept selection](coder-genesis-bootstrap-concept-selection.md)
- detail: [coder genesis bootstrap guide](coder-genesis-bootstrap-guide.md)
