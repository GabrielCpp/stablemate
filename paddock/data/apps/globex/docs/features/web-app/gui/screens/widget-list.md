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
- exclusive-with: [empty-notice](#empty-notice), [load-alert](#load-alert)
- states: populated — visible, one row per widget, `name` and `quantity` in each row
- verify: visible(locator="#widget-table")
- fixture: widgets-on-hand — the directory holds at least one widget
- states: loading — not yet drawn while the fetch is pending
- code: `app/web-app/static/app.js::renderWidgetTable` @a9a308e1d664
- detail: which of the three the page shows is recorded once, as `exclusive-with:`, and each
  of the three states what it looks like when it is the one shown. Saying it a second time
  here — that the table is hidden when the notice is up — would be the same claim in two
  places, and the vocabulary has no check that observes an element being absent from the
  screen in any case. The loading state carries no arrangement because none exists: it holds
  only while the fetch is in flight, and nothing outside the page can hold it there.
- fixture:
- tests:

### empty-notice
- selector: p.empty-notice
- role: status
- one-per:
- variants:
- name: No widgets are on file yet.
- unique-by:
- placement:
- keyboard:
- extends:
- parent:
- exclusive-with: [widget-table](#widget-table), [load-alert](#load-alert)
- states: shown — visible whenever the directory read succeeds and returns no widgets
- verify: visible(locator="#empty-notice")
- fixture: empty-directory — the directory holds no widgets
- code: `app/web-app/static/app.js::renderWidgetTable` @a9a308e1d664
- detail:
- tests:

### load-alert
- selector: p[role="alert"]
- role: alert
- one-per:
- variants:
- name: Could not read the widget directory.
- unique-by:
- placement:
- keyboard:
- extends:
- parent:
- exclusive-with: [widget-table](#widget-table), [empty-notice](#empty-notice)
- states: shown — visible whenever the directory read itself fails, carrying the reason rather
  than an empty table that would read as a directory with nothing in it
- verify: visible(locator="#load-alert")
- fixture: api-service-unavailable — the directory read fails
- code: `app/web-app/static/app.js::loadWidgets` @a9a308e1d664
- detail:
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
- verify: visible(locator="new-widget.md#new-widget-form")
- code: `app/web-app/static/index.html` @55269916a58e
- detail:
- fixture:
- capture:
- tests:
