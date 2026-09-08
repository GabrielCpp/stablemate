---
type: concept
slug: dashboard-wire-events-scope
title: Dashboard wire events scope
---
# Dashboard wire events scope

`wireEvents` is called once, at dashboard initialization, and registers every
browser-native listener the dashboard uses for the rest of the page session —
repository-picker input and menu clicks, the activity-bar mode switch, the
runs and traces filters, the delegated body click that routes worker
selection, refresh, and the command palette, the palette's own input and
keyboard navigation, the global `j`/`k`/`Escape`/`Ctrl+K` shortcuts, and the
one-time first-click [browser notification permission](browser-notification-permission.md)
bootstrap. Each listener closes over its own DOM targets and dispatches on its
own event; none of them re-implements another's concern; and none is called
by, delegates to, or supersedes another.

- code: groom/groom/assets/dashboard.js
- rule: `wireEvents` is a single registration point for unrelated,
  independently reachable browser-event concerns, not a set of alternative
  implementations of one operation. The source records no preference,
  deprecation, or successor relationship among the concepts it grounds — pick
  the one whose concern matches the operator's event target or shortcut.

