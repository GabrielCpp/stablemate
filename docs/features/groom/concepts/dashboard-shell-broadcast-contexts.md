---
type: concept
slug: dashboard-shell-broadcast-contexts
title: Dashboard shell broadcast contexts
---
# Dashboard shell broadcast contexts

The dashboard shell broadcaster is one shared implementation, not two alternative
broadcast mechanisms. The surrounding lifecycle chooses the journey that reaches
it. Startup discovery clears the initial scanning state after its background
reconciliation pass and then broadcasts to dashboard tabs already connected to
the new server. A manual refresh sets scanning and broadcasts before reconciliation,
then clears scanning and broadcasts the completed fleet after a successful pass.

Both contexts are current. Use [serve dashboard and startup discovery](../flows/serve-dashboard-and-startup-discovery.md)
to describe serving a new groom process and its one-shot startup scan; use
[operator refreshes workflow fleet](../flows/operator-refreshes-workflow-fleet.md)
to describe an operator-requested reconciliation of an already-running process.
Neither flow supersedes the other: their different scanning-state transitions and
initiation conditions are required by their callers.

- rule: use startup discovery when process startup schedules the one-shot reconciliation; use manual refresh when an operator requests reconciliation of an already-running fleet; neither context is deprecated
