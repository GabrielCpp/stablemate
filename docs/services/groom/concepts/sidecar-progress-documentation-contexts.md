---
type: concept
slug: sidecar-progress-documentation-contexts
title: Sidecar progress documentation contexts
---
# Sidecar progress documentation contexts

`_apply_socket_progress` is the one connected-sidecar progress handler: it records the
reported current node, moves the workflow to `running`, and broadcasts the changed dashboard
shell. The [sidecar progress applier](sidecar-progress-applier.md) describes that handler's
application work, while [transition-sidecar-progress](workflow-state.md#transition-sidecar-progress)
describes its resulting workflow-state transition. Both describe the same current path; neither
is a replacement for the other.

Read [method-apply-socket-progress](groom-app-module.md#method-apply-socket-progress) when
choosing or understanding the server operation, and read
[transition-sidecar-progress](workflow-state.md#transition-sidecar-progress) when determining
the lifecycle effect. The socket dispatch in `groom/groom/app.py::dashboard_sidecar` invokes
`groom/groom/app.py::_apply_socket_progress` only for a `progress` frame after a sidecar
connection has been established, so this context does not describe the separate HTTP progress
push path.

- rule: use the method for the connected-sidecar handler contract and the transition for its workflow-state effect; neither node is preferred because they document complementary views of the same operation.
