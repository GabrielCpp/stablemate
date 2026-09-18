---
type: screen
slug: new-widget
title: Add a widget
---
# Add a widget

Reached from [widget-list](widget-list.md)'s `open-new-widget` interaction. Submitting the
form here is the device's own network POST to
[api-service](../../../api-service/http/api-service.md) — the screen makes the request itself,
which is why a Maestro journey through this screen can assert the code the screen's own request
carried, but never substitute an HTTP client for the tap.

- route: /new
- requires:
- params:
- entry: [open-new-widget](widget-list.md#open-new-widget)
- detail:

## Components

### name-field
- selector: testID=name-input
- role: textbox
- one-per:
- variants:
- name: Name
- unique-by:
- placement:
- keyboard: none
- extends:
- parent: [new-widget-screen](#new-widget-screen)
- exclusive-with:
- states:
  - invalid: `#name-error` carries the field's error message
- verify: visible(locator="#name-field")
- fixture:
- code: `app/mobile-app/src/screens/NewWidgetScreen.tsx::NewWidgetScreen` @299b86627495
- detail: `textbox` is the honest computed role for a plain `TextInput` — React Native gives it
  no accessibility role of its own beyond being an editable text field. The source sets
  `accessibilityLabel="Name"` on this input directly, so `name:` is that observed prop rather
  than the adjacent `Text` reading "Name" above it, which is not programmatically associated
  with the input.
- tests:

### quantity-field
- selector: testID=quantity-input
- role: textbox
- one-per:
- variants:
- name: Quantity
- unique-by:
- placement:
- keyboard: none
- extends:
- parent: [new-widget-screen](#new-widget-screen)
- exclusive-with:
- states:
  - invalid: `#quantity-error` carries the field's error message
- verify: visible(locator="#quantity-field")
- fixture:
- code: `app/mobile-app/src/screens/NewWidgetScreen.tsx::NewWidgetScreen` @299b86627495
- detail: `keyboardType="numeric"` only changes which software keyboard the device shows; it
  does not change the control's accessibility role the way HTML's `type="number"` maps to
  ARIA's `spinbutton` on the web. So this field is `textbox`, not the `spinbutton`
  [web-app](../../../web-app/gui/screens/new-widget.md#quantity-field) states for its own
  `#quantity` — a deliberate divergence, not a copy error. The source sets
  `accessibilityLabel="Quantity"` on this input directly, so `name:` is that observed prop.
- tests:

### name-error
- selector: testID=name-error
- role: alert
- one-per:
- variants:
- name: Name: <message>
- unique-by:
- placement:
- keyboard: none
- extends:
- parent: [new-widget-screen](#new-widget-screen)
- exclusive-with:
- states:
  - invalid: populated from the refusal branch of `submit-new-widget`
- verify: visible(locator="#name-error")
- fixture:
- code: `app/mobile-app/src/screens/NewWidgetScreen.tsx::renderFieldError` @299b86627495
- detail: `renderFieldError` sets `role="alert"` explicitly and renders nothing when there is no
  message — one state, not two, for the same reason
  [web-app](../../../web-app/gui/screens/new-widget.md#name-error) declares only `invalid`: no
  check in this vocabulary observes an element being absent, so "absent on arrival" would be an
  undischargeable claim sitting beside a dischargeable one. The source sets
  `accessibilityLabel={`Name: ${message}`}` (`fieldLabel` is the literal `"Name"` at this call
  site), so `name:` states that template rather than a bare `none` — the static `"Name: "`
  prefix is what distinguishes this alert from `quantity-error`'s, whose own prefix is
  `"Quantity: "`. `parent:` is [new-widget-screen](#new-widget-screen) rather than `name-field`:
  this element and `quantity-error` cite the same `renderFieldError` symbol as a shared call —
  they are both regions of the one form root's render, not two rival implementations of one
  thing, and that is the true containment the `parent:` mechanism asks for.
- tests:

### quantity-error
- selector: testID=quantity-error
- role: alert
- one-per:
- variants:
- name: Quantity: <message>
- unique-by:
- placement:
- keyboard: none
- extends:
- parent: [new-widget-screen](#new-widget-screen)
- exclusive-with:
- states:
  - invalid: populated from the refusal branch of `submit-new-widget`
- verify: visible(locator="#quantity-error")
- fixture:
- code: `app/mobile-app/src/screens/NewWidgetScreen.tsx::renderFieldError` @299b86627495
- detail: the same `renderFieldError` helper `name-error` cites, called a second time with
  `fieldLabel="Quantity"` for the `quantity` field's own message — hence `name:`'s
  `"Quantity: "` prefix, distinct from `name-error`'s `"Name: "`. `parent:` is
  [new-widget-screen](#new-widget-screen) for the same reason as `name-error`: both alerts are
  regions of the one form root's render sharing one helper, not rival implementations of it.
- tests:

### submit-widget-button
- selector: testID=submit-widget
- role: button
- one-per:
- variants:
- name: Add widget
- unique-by:
- placement:
- keyboard: none
- extends:
- parent: [new-widget-screen](#new-widget-screen)
- exclusive-with:
- states:
- verify: visible(locator="#submit-widget-button")
- fixture:
- code: `app/mobile-app/src/screens/NewWidgetScreen.tsx::NewWidgetScreen` @299b86627495
- detail: the source sets `role="button"` explicitly on this `Pressable`, the same observed
  prop as [widget-list](widget-list.md#new-widget-link)'s `new-widget-link` — `button` is
  name-from-content, so `name:` is the control's own text.
- tests:

### new-widget-screen
- selector: testID=new-widget-screen
- role: none
- one-per:
- variants:
- name: none
- unique-by:
- placement:
- keyboard:
- extends:
- parent:
- exclusive-with:
- states:
- verify: visible(locator="#new-widget-screen")
- fixture:
- code: `app/mobile-app/src/screens/NewWidgetScreen.tsx::NewWidgetScreen` @299b86627495
- detail: the root view the two fields sit in — the arrival marker
  [widget-list](widget-list.md)'s `open-new-widget` observes on arrival, the same job
  [web-app](../../../web-app/gui/screens/new-widget.md#new-widget-form)'s `new-widget-form`
  does for its own screen. `role:` is `none` because it is a plain structural container with no
  interactive semantics of its own.
- tests:

## Interactions

### submit-new-widget
- on: [submit-widget-button](#submit-widget-button)
- trigger: tap
- role: button
- one-per:
- variants:
- name: Add widget
- unique-by:
- keyboard: none
- verify: actionable(locator="#submit-widget-button")
- when: `name` non-empty and `quantity` a non-negative number
- exclusive-with:
- extends:
- does:
  - the app navigates to [widget-list](widget-list.md)
- verify: visible(locator="widget-list.md#widget-table")
- verify: http_status(201, method="POST", path="/api/widgets")
- fixture:
- arrange: fill(locator="#name-field", value="Widget A")
- arrange: fill(locator="#quantity-field", value="3")
- capture:
- code: `app/mobile-app/src/screens/NewWidgetScreen.tsx::submitNewWidget` @299b86627495
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
  - the field error texts are populated from the response body, and the screen stays put — the
    form is still the thing on screen
- verify: visible(locator="#name-error")
- verify: visible(locator="#new-widget-screen")
- verify: http_status(422, method="POST", path="/api/widgets")
- fixture:
- arrange: fill(locator="#name-field", value="")
- arrange: fill(locator="#quantity-field", value="-1")
- capture:
- code: `app/mobile-app/src/screens/NewWidgetScreen.tsx::submitNewWidget` @299b86627495
- detail: the refusal arm — same button, same trigger, same control identity as
  [submit-new-widget](#submit-new-widget), inherited through `extends:` rather than repeated.
- tests:
