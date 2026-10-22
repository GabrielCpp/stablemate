---
type: concept
slug: sidecar-blocked-documentation-scope
title: Sidecar blocked documentation scope
---
# Sidecar blocked documentation scope

`groom/groom/app.py::_apply_socket_blocked` has one implementation and no alternative code path;
the [sidecar blocked applier](sidecar-blocked-applier.md) and the
[sidecar blocked update context](sidecar-blocked-update-context.md) both cite it because they
document that one callable at different scopes, not because a choice between implementations
exists.

Use the sidecar blocked applier for the callable's complete precondition, input-handling, gate,
broadcast, and failure-semantics contract. Use the sidecar blocked update context when relating
that callable's effect to the [sidecar blocked transition](workflow-state.md#transition-sidecar-blocked)
it produces — the same update viewed from the lifecycle-state side rather than the handler side.
Neither node is preferred or deprecated: read the applier for the handler's own behavior and the
update context for how that behavior composes with the workflow's lifecycle state.

- rule: select the documentation context by the question being asked; `_apply_socket_blocked` has one current implementation and no ranking between the handler-level applier and the lifecycle-relating update context
