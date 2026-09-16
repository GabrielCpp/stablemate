---
type: screen
slug: new-widget
title: Add a widget
---
# Add a widget

Reached from [widget-list](widget-list.md)'s `open-new-widget` interaction. Submitting the
form here is the browser's own cross-origin POST to
[api-service](../../../api-service/http/api-service.md) — the page makes the request itself,
which is why a Playwright journey through this screen can assert the code the page's own
request carried, but never substitute an HTTP client for the click.

- route: /new.html
- requires:
- params:
- entry: [open-new-widget](widget-list.md#open-new-widget)
- detail:

## Components

### name-field
- selector: #name
- role: textbox
- one-per:
- variants:
- name: Name
- unique-by:
- placement:
- keyboard: reachable by Tab
- extends:
- parent:
- exclusive-with:
- states:
  - invalid: `#name-error` carries the field's error message
- verify: visible(locator="#name")
- code: `app/web-app/static/new.html` @bf0832921aaf
- detail:
- fixture:
- tests:

### quantity-field
- selector: #quantity
- role: spinbutton
- one-per:
- variants:
- name: Quantity
- unique-by:
- placement:
- keyboard: reachable by Tab
- extends:
- parent:
- exclusive-with:
- states:
  - invalid: `#quantity-error` carries the field's error message
- verify: visible(locator="#quantity")
- code: `app/web-app/static/new.html` @bf0832921aaf
- detail:
- fixture:
- tests:

## Interactions

### submit-new-widget
- on: [name-field](#name-field), [quantity-field](#quantity-field)
- trigger: click
- role: button
- one-per:
- variants:
- name: Add widget
- unique-by:
- keyboard: Enter (while a field has focus), or click
- when: `name` non-empty and `quantity` a non-negative number
- exclusive-with:
- does:
  - success: browser navigates to [widget-list](widget-list.md)
  - failure: field error spans are populated from the response body
  - failure: page stays put (no navigation)
- verify: visible(locator="table[aria-label='Widgets on hand']")
- verify: http_status(201, path="/api/widgets")
- code: `app/web-app/static/new.js::submitNewWidget` @6f983e4202a9
- detail:
- fixture:
- capture:
- tests:
