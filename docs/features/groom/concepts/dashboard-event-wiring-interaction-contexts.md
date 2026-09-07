---
type: concept
slug: dashboard-event-wiring-interaction-contexts
title: Dashboard event wiring interaction contexts
---
# Dashboard event wiring interaction contexts

`wireEvents` is the dashboard's one-time browser event registration point. Its
handlers serve separate controls and gestures: filtering runs, opening and
searching the repository menu, choosing a run with `j` or `k`, requesting
notification permission, and toggling the command palette. They are not
alternative implementations of one operation.

Choose the interaction that matches the operator's event target or shortcut.
The repository-picker interactions share menu mechanics but differ by the
active Files or Diff pane; the remaining interactions operate on their own
control or global shortcut. The source records no preferred or deprecated
handler because all seven contexts are current and independently reachable.

- code: `groom/groom/assets/dashboard.js::wireEvents`
- rule: use the interaction for the operator's event target or keyboard shortcut; the shared wiring function does not rank its independently current handlers
