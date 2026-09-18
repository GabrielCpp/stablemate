---
type: flow
slug: browse-and-add-widget
title: Browse and add a widget
---
# Browse and add a widget

One person, one device, moving between mobile-app's two screens: they land on the directory,
find it empty or not, follow the link to the form, and submit a new widget. Every step in this
flow is something the device does — arranging a known starting state (seeding a widget through
api-service before the journey begins, so the empty-state and populated-state assertions are
both reachable) is allowed before the journey starts, but no step drives an HTTP client as a
stand-in for the user. This is the same "user crossing" shape
[web-app's browse-and-add-widget](../../web-app/flows/browse-and-add-widget.md) walks, driven
from a device instead of a browser: one actor moving between the two screens
[widget-list](../gui/screens/widget-list.md) and [new-widget](../gui/screens/new-widget.md),
against the one [api-service](../../api-service/http/api-service.md) both clients share.

- start: [widget-list](../gui/screens/widget-list.md)
- steps:
  - [open-new-widget](../gui/screens/widget-list.md#open-new-widget)
  - [submit-new-widget](../gui/screens/new-widget.md#submit-new-widget)
- end: [widget-list](../gui/screens/widget-list.md)
- verify: visible(locator="../gui/screens/widget-list.md#widget-table")
- fixture: none, because the flow itself creates the widget it later observes — the journey
  starts from the empty directory the Maestro flow file asserts and the submission step is what
  populates it
- detail: the Maestro flow file `app/mobile-app/.maestro/browse-and-add-widget.flow.yaml` drives
  this same journey against a freshly started api-service, so the empty-state assertion and the
  populated-state assertion both come from the one run.
- tests:
