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
- verify: visible(locator="#name-field")
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
- verify: visible(locator="#quantity-field")
- code: `app/web-app/static/new.html` @bf0832921aaf
- detail:
- fixture:
- tests:

### name-error
- selector: #name-error
- role:
- one-per:
- variants:
- name:
- unique-by:
- placement:
- keyboard:
- extends:
- parent: [name-field](#name-field)
- exclusive-with:
- states:
- verify: visible(locator="#name-error")
- code: `app/web-app/static/new.html` @bf0832921aaf
- detail: the span `name-field`'s `invalid` state names. Declared because the refusal branch
  of `submit-new-widget` is observed through it, and a check's locator names a component this
  book declares rather than a CSS id nothing here has heard of.
- fixture:
- tests:

### new-widget-form
- selector: #new-widget-form
- role: none
- one-per:
- variants:
- name:
- unique-by:
- placement:
- keyboard:
- extends:
- parent:
- exclusive-with:
- states:
- verify: visible(locator="#new-widget-form")
- code: `app/web-app/static/new.html` @bf0832921aaf
- detail: the form element the two fields sit in. Declared because it is what
  `widget-list`'s `open-new-widget` observes on arrival — the screen is reached when the form
  is on it, and an interaction that lands here needs something in this book to point at.
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
- does: on acceptance, the browser navigates to [widget-list](widget-list.md)
- verify: visible(locator="widget-list.md#widget-table")
- verify: http_status(201, path="/api/widgets")
- does: on refusal, the field error spans are populated from the response body
- verify: visible(locator="#name-error")
- verify: http_status(400, path="/api/widgets")
- does: on refusal, the page stays put — the form is still the thing on screen
- verify: visible(locator="#new-widget-form")
- code: `app/web-app/static/new.js::submitNewWidget` @6f983e4202a9
- detail:
- fixture:
- capture:
- tests:
