---
type: concept
slug: workflow-upsert-documentation-contexts
title: Workflow upsert documentation contexts
---
# Workflow upsert documentation contexts

`upsert_workflow` has one implementation, not two alternatives. It creates a missing
`WorkflowContainer` with its dataclass defaults, including `idle` state, then assigns only
supplied, non-`None` names that already exist on that stored container.

Use the [Groom state module method](groom-state-module.md#method-upsert-workflow) for the
call's complete registry contract: creation, display-name fallback, partial updates, and the
returned mutable container. Use the [workflow-state transition](workflow-state.md#transition-registry-default-and-assignment)
when the question is limited to the lifecycle field: why a new partial record is `idle`, when
a supplied non-null state replaces it, and why omitted or `None` state leaves it unchanged.
Neither view supersedes the other; the transition is the state-specific consequence of the
same registry operation.

- code: groom/groom/state.py::upsert_workflow
- rule: use the registry method for the full upsert contract and the workflow-state transition for lifecycle defaulting or assignment within that contract
