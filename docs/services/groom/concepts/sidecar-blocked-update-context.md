---
type: concept
slug: sidecar-blocked-update-context
title: Sidecar blocked update context
---
# Sidecar blocked update context

The connected-sidecar `blocked` delta and the resulting workflow-state transition
describe one update at different levels. The [sidecar blocked applier](sidecar-blocked-applier.md)
documents the handler's precondition, input handling, gate replacement, broadcasts, and
reconciliation. The [sidecar blocked transition](workflow-state.md#transition-sidecar-blocked)
documents the lifecycle result that the handler makes visible to the rest of Groom.

Use the applier when following a decoded `blocked` frame after the sidecar session has
accepted `hello` and registered its connection. Use the transition when determining how
that frame changes a workflow's lifecycle state. Neither is a substitute for the other:
the session dispatcher calls `_apply_socket_blocked` only for a connected sidecar's
`blocked` frame, and the function then records the workflow as `BLOCKED`.

- code: groom/groom/app.py::_apply_socket_blocked
- rule: use the sidecar blocked applier for connected-sidecar delta handling and the sidecar blocked transition for its workflow-state result; neither is a ranked alternative
- detail: [sidecar blocked documentation scope](sidecar-blocked-documentation-scope.md)
