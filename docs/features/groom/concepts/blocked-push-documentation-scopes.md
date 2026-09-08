---
type: concept
slug: blocked-push-documentation-scopes
title: Blocked push documentation scopes
---
# Blocked push documentation scopes

`push_blocked` accepts the common HTTP payload from either the sidecar or the
`await_operator.py` backstop, rejects a missing container id or gate path, hydrates
volume metadata, upserts the workflow, records the gate, broadcasts refreshed dashboard
state and detail, notifies browser clients, and schedules a reconciliation poll. Its source
assigns `WorkflowState.BLOCKED` as part of that endpoint operation.

The [push blocked method](groom-app-module.md#method-push-blocked) and the [blocked push
transition](workflow-state.md#transition-blocked-push) are both current views of that one
function, not alternatives. Use the method for the endpoint's complete input, side effects,
and notification contract. Use the transition when following only how a blocked push changes
the workflow lifecycle; it deliberately omits the endpoint behavior that does not define the
state transition. Neither view supersedes the other.

- code: groom/groom/app.py::push_blocked
- rule: use the method for the complete blocked-push endpoint contract; use the workflow-state transition only for its `BLOCKED` lifecycle effect
- detail: [blocked push documentation index](blocked-push-documentation-index.md)
