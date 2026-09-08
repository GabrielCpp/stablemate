---
type: concept
slug: sidecar-session-and-workflow-state
title: Sidecar session and workflow state
---
# Sidecar session and workflow state

The sidecar websocket has one connection lifecycle and one separate workflow-state
consequence. `dashboard_sidecar` accepts the socket, creates and registers a
connection only after a usable `hello` identity, dispatches later frames through
that connection, and unregisters that same connection in its `finally` cleanup.

Use [dashboard sidecar](groom-app-module.md#method-dashboard-sidecar) to understand
the websocket session, accepted frame sequence, RPC resolution, and connection
cleanup. Use [sidecar disconnect leaves workflow state unchanged](workflow-state.md#transition-sidecar-disconnect-no-state-change)
to understand the lifecycle-state consequence of that cleanup: unregistering the
live connection does not itself supply lifecycle evidence or change the workflow
record. Neither node supersedes the other; they describe different concerns of the
same session path.

- code: groom/groom/app.py::dashboard_sidecar
- rule: use the session method for transport behavior and the transition for the workflow-state effect of disconnect; neither is a replacement for the other.
