---
type: flow
slug: browse-and-add-widget
title: Browse and add a widget
---
# Browse and add a widget

One person, one browser, moving between web-app's two screens: they land on the directory,
find it empty or not, follow the link to the form, and submit a new widget. Every step in
this flow is something the browser does — arranging a known starting state (seeding a
widget through api-service before the journey begins, so the empty-state and populated-state
assertions are both reachable) is allowed before the journey starts, but no step drives an
HTTP client as a stand-in for the user. This is the "user crossing": one actor moving
between the two screens [widget-list](../../web-app/gui/screens/widget-list.md) and
[new-widget](../../web-app/gui/screens/new-widget.md), as opposed to
[add-widget-via-api](../../api-service/flows/add-widget-via-api.md), which is web-app's own
stack crossing into api-service and not part of this journey at all.

- start: [widget-list](../gui/screens/widget-list.md)
- steps:
  - [open-new-widget](../gui/screens/widget-list.md#open-new-widget)
  - [submit-new-widget](../gui/screens/new-widget.md#submit-new-widget)
- end: [widget-list](../gui/screens/widget-list.md)
- verify: visible(locator="../gui/screens/widget-list.md#widget-table")
- fixture: widgets-on-hand — the directory holds one widget, so the table has a row to
  render on arrival
- detail: seed one widget via `POST /api/widgets` before the journey starts so the table is
  non-empty on arrival; the journey itself never calls the API directly.
- tests:
