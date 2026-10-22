---
type: concept
slug: dashboard-websocket-flow-contexts
title: Dashboard websocket flow contexts
---
# Dashboard websocket flow contexts

`dashboard_ws` is the one per-tab session implementation for the dashboard socket:
it accepts the tab, registers its outbound queue, sends the initial state snapshot,
and then runs the send and receive loops until either finishes. The flows describe
different contexts that reach that same session rather than alternative ways to
implement it.

Use [serve dashboard and startup discovery](../flows/serve-dashboard-and-startup-discovery.md)
when a newly served groom process accepts a tab and establishes its initial state.
Use [operator answers blocked gate](../flows/operator-answers-blocked-gate.md) when
an established tab sends the `answer` command for an open gate. Both contexts are
current: the handler has no source-level preference because startup establishes the
session that the answer journey subsequently uses.

- code: groom/groom/app.py::dashboard_ws
- rule: use startup discovery to document session establishment during process startup; use the blocked-gate flow to document an answer command sent through an established session; neither flow is deprecated or preferred
