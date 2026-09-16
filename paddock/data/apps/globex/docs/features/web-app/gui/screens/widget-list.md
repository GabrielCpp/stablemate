---
type: screen
slug: widget-list
title: Widget directory
---
# Widget directory

The landing page web-app serves. It reads the whole widget directory from
[api-service](../../../api-service/http/api-service.md) over a cross-origin `fetch` made by
the page itself — the browser is the only thing that talks to both services, which is what
makes this screen the "user crossing" endpoint of the fixture rather than a client to be
driven directly.

- route: /
- requires:
- params:
- entry: direct navigation, or returning from [new-widget](new-widget.md) after a
  successful submission
- detail:

## Components

### widget-table
- selector: table[aria-label="Widgets on hand"]
- role: table
- one-per:
- variants:
- name: Widgets on hand
- unique-by:
- placement:
- keyboard:
- extends:
- parent:
- exclusive-with: [empty notice](#widget-table) hidden state is exclusive with the alert
  and the populated table
- states:
  - loading: neither table nor empty notice nor alert is shown while the fetch is pending
  - populated: visible, one row per widget, `name` and `quantity` in each row
  - empty: hidden; `p.empty-notice` shown instead
  - error: hidden; `p[role="alert"]` shown instead
- verify: visible(locator="table[aria-label='Widgets on hand']")
- code: `app/web-app/static/app.js::renderWidgetTable` @a9a308e1d664
- detail:
- fixture:
- tests:

### new-widget-link
- selector: #new-widget-link
- role: link
- one-per:
- variants:
- name: Add a widget
- unique-by:
- placement:
- keyboard: reachable by Tab, activates on Enter
- extends:
- parent:
- exclusive-with:
- states:
- verify: visible(locator="#new-widget-link")
- code: `app/web-app/static/index.html` @55269916a58e
- detail:
- fixture:
- tests:

## Interactions

### open-new-widget
- on: [new-widget-link](#new-widget-link)
- trigger: click
- role: link
- one-per:
- variants:
- name: Add a widget
- unique-by:
- keyboard: Enter
- when:
- exclusive-with:
- does:
  - navigation: browser navigates to [new-widget](new-widget.md)
- verify: visible(locator="#new-widget-form")
- code: `app/web-app/static/index.html` @55269916a58e
- detail:
- fixture:
- capture:
- tests:
