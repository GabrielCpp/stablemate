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
- fixture:
- code: `app/web-app/static/new.html` @18dfea321e64
- detail:
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
- fixture:
- code: `app/web-app/static/new.html` @18dfea321e64
- detail:
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
  - invalid: populated from the refusal branch of `submit-new-widget`
- verify: visible(locator="#name-error")
- fixture:
- code: `app/web-app/static/new.html` @18dfea321e64
- detail: the span `name-field`'s `invalid` state names. Declared because the refusal branch
  of `submit-new-widget` is observed through it, and a check's locator names a component this
  book declares rather than a CSS id nothing here has heard of. It carries one state and not
  two: "absent on arrival" was written here and taken out, because no check in this book's
  vocabulary observes an element being absent from the screen, so it was a claim nothing could
  ever discharge sitting in the same bullet as one that can — and whichever scenario read the
  bullet would have been credited with both.
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
- fixture:
- code: `app/web-app/static/new.html` @18dfea321e64
- detail: the form element the two fields sit in. Declared because it is what
  `widget-list`'s `open-new-widget` observes on arrival — the screen is reached when the form
  is on it, and an interaction that lands here needs something in this book to point at.
- tests:

### submit-widget-button
- selector: #submit-widget
- role: button
- one-per:
- variants:
- name: Add widget
- unique-by:
- placement:
- keyboard: reachable by Tab
- extends:
- parent: [new-widget-form](#new-widget-form)
- exclusive-with:
- states:
- verify: visible(locator="#submit-widget-button")
- fixture:
- code: `app/web-app/static/new.html` @18dfea321e64
- detail:
- tests:

## Interactions

### submit-new-widget
- on: [submit-widget-button](#submit-widget-button)
- trigger: click
- role: button
- one-per:
- variants:
- name: Add widget
- unique-by:
- keyboard: Enter (while a field has focus), or click
- verify: focusable(locator="#submit-widget-button", activates="Enter")
- when: `name` non-empty and `quantity` a non-negative number
- arrange: fill(locator="#name-field", value="Widget A")
- arrange: fill(locator="#quantity-field", value="3")
- exclusive-with:
- does:
  - the browser navigates to [widget-list](widget-list.md)
- verify: visible(locator="widget-list.md#widget-table")
- verify: http_status(201, path="/api/widgets")
- fixture:
- capture:
- code: `app/web-app/static/new.js::submitNewWidget` @6f983e4202a9
- detail: the base case — the form's `name`/`quantity` both satisfy `when:`, so the service
  accepts the widget. [refuse-new-widget](#refuse-new-widget) extends this arm for the case it
  does not.
- tests:

### refuse-new-widget
- on:
- trigger:
- role:
- one-per:
- variants:
- name:
- unique-by:
- keyboard:
- when: `name` empty, or `quantity` missing or negative
- exclusive-with:
- extends: [submit-new-widget](#submit-new-widget)
- does:
  - the field error spans are populated from the response body, and the page stays put — the form is still the thing on screen
- verify: visible(locator="#name-error")
- verify: visible(locator="#new-widget-form")
- verify: http_status(422, path="/api/widgets")
- fixture:
- capture:
- code: `app/web-app/static/new.js::submitNewWidget` @6f983e4202a9
- detail: the refusal arm — same button, same trigger, same control identity as
  [submit-new-widget](#submit-new-widget), inherited through `extends:` rather than repeated.
- tests:
