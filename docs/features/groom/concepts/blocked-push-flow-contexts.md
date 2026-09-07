---
type: concept
slug: blocked-push-flow-contexts
title: Blocked push flow contexts
---
# Blocked push flow contexts

`push_blocked` is the common host endpoint for a blocked-gate notification
from either `groom-sidecar` or the `await_operator.py` backstop. It accepts
the same payload and applies the same blocked workflow state, gate record,
dashboard refresh, notification, and immediate reconciliation regardless of
which producer arrives first. A second delivery is a harmless re-render;
the run's own `questions` listing remains authoritative for the gate.

The [blocked push payload](../blocked-push-payload.md) is the input to this
operation: producers use it to tell Groom which gate blocked. The [dashboard
notify message](../dashboard-notify-message.md) is the output edge from the
same operation: Groom broadcasts it after the state and detail refresh so
connected tabs interrupt the operator. They are not interchangeable wire
formats or alternative ways to report a block; one request may produce one
notification frame.

Read [operator answers blocked gate](../flows/operator-answers-blocked-gate.md)
when following an already-visible gate through the dashboard answer journey.
Read [residual sidecar push and query fallback](../flows/residual-sidecar-push-and-query-fallback.md)
when following the sidecar, backstop, discovery, or fallback routes that can
deliver the blocked notification. Neither flow supersedes the other: they
describe different contexts that converge on the same endpoint.

- code: groom/groom/app.py::push_blocked
- rule: use the blocked push payload to report a gate to `push_blocked`; consume the dashboard notify message only as the resulting server-to-browser interruption
