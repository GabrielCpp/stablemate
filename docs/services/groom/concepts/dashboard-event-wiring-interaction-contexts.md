---
type: concept
slug: dashboard-event-wiring-interaction-contexts
title: Dashboard event wiring interaction contexts
---
# Dashboard event wiring interaction contexts

`wireEvents` is the dashboard's one-time browser event registration point. Its
handlers serve separate controls and gestures: switching panels from the
activity bar, filtering runs, selecting a run by click or with `j` or `k` unless focus is in a text field, text area or select, refreshing the fleet,
opening the command palette from its button or with Ctrl or Cmd plus `k`,
navigating and choosing palette results, opening and closing the new-run
dispatch dialog, closing every open overlay with Escape, keeping Tab inside
the palette and the dispatch dialog, and requesting
[notification permission](browser-notification-permission.md) on the first
click. They are not alternative implementations of one operation.

Choose the interaction that matches the operator's event target or shortcut.
Every interaction, including the
[browser notification permission](browser-notification-permission.md)
requests, operates on their own control or global shortcut. The source
records no preferred or deprecated handler because every context is current
and independently reachable.

- code: `groom/groom/assets/dashboard.js::wireEvents` @f16e2d670990
- rule: use the interaction for the operator's event target or keyboard shortcut; the shared wiring function does not rank its independently current handlers
- detail: [browser notification permission](browser-notification-permission.md)
- detail: [dashboard wire events scope](dashboard-wire-events-scope.md)
