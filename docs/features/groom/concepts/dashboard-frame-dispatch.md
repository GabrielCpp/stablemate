---
type: concept
slug: dashboard-frame-dispatch
title: Dashboard frame dispatch
---
# Dashboard frame dispatch

The dashboard dispatches every received websocket frame by its `type` member. The `notify` and
`answered` branches are both current and neither is a substitute for the other: `notify` reports
a newly blocked workflow or fired alert rule and interrupts the operator with alert content;
`answered` confirms that a gate answer succeeded after the accompanying state and detail pushes
have already refreshed the visible dashboard.

Choose the frame by the event it represents, not by a preference between handlers. A sender that
needs to alert every connected tab about a blocked workflow or alert uses `notify`; a successful
gate-answer command uses `answered` solely to acknowledge completion. The dispatcher routes
`notify` to `onNotify(message)` and `answered` to `onAnswered()`, so each handler receives only
the payload its frame contract supplies.

- code: groom/groom/assets/dashboard.js::onFrame
- rule: use `notify` for a blocking or alert event and `answered` only to acknowledge a successful gate answer; neither frame supersedes the other
