---
type: concept
slug: dashboard-toast-pusher
title: Dashboard toast pusher
---
# Dashboard toast pusher

Dashboard toast pusher is the groom dashboard's in-page notification helper. It appends transient toast DOM nodes to the [groom dashboard](../gui/screens/groom-dashboard.md) `#toasts` host when a [blocked notification script fragment](../blocked-notification-script-fragment.md) dispatches `groom:blocked` or when a [groom answered script fragment](../groom-answered-script-fragment.md) dispatches `groom:answered`; [browser notification permission](browser-notification-permission.md) only gates the optional system notification and never gates these in-page toasts.

- code: groom/groom/templates/dashboard.html::pushToast
- code: groom/groom/templates/dashboard.html::document.body.addEventListener("groom:blocked")
- code: groom/groom/templates/dashboard.html::document.body.addEventListener("groom:answered")
- code: groom/groom/assets/dashboard.css::#toasts,.toast

## Contract

- purpose: show short-lived, page-local confirmation or blocked-work notifications without changing server state, browser route, selected worker, selected repository, websocket connection, or notification permission.
- trigger model: the helper is not invoked directly by server-rendered HTML; browser-executed inline script fragments dispatch CustomEvents on `document.body`, and dashboard listeners call the helper from those events.
- host: every toast is appended to the existing `#toasts` element at the end of the dashboard body.
- ordering: newer toasts are appended after older toasts in DOM order; the CSS host stacks them as a fixed vertical column.
- lifetime: each toast schedules its own removal with `setTimeout`; no shared queue, cancellation, deduplication, persistence, or maximum-count trimming exists.
- content safety: title and body values are assigned through `textContent`, so markup-like message text is displayed as text rather than interpreted as HTML.
- blocked event behavior: `groom:blocked` always pushes one `blocked` toast titled `⛔ worker blocked` with the event detail string or fallback body `A workflow needs your input.` and a 7000 ms lifetime, independent of Notification API availability or permission state.
- answered event behavior: `groom:answered` always pushes one `ok` toast titled `✓ answer sent`, omits a body node, and uses a 3500 ms lifetime before optionally refreshing the selected worker detail when the event detail id matches the selected worker.
- visual placement: the toast host is fixed at the lower-right of the viewport with a high z-index; individual toasts are 300 px wide cards with a dark background, border, left accent stripe, small title, optional single-line body, shadow, and slide-in animation.
- variant styling: the default/blocked toast uses the blocked accent color; the `ok` variant overrides only the left accent stripe with the running/success color.
- accessibility gap: generated toast nodes have no `role`, no accessible name beyond ordinary text content, no `aria-live` region, no focus movement, no keyboard interaction, and no close control, so screen-reader announcement of dynamically inserted toasts is not guaranteed.
- error handling: missing `#toasts`, DOM append failures, invalid timeout values, and timer failures are not caught or transformed by groom.
- excluded effects: the helper does not create system browser notifications, request Notification permission, send HTTP requests, send websocket messages, mutate workflow containers, mutate gate records, update the inbox/status fragments, refresh worker detail, or navigate.

## Fields

### field-toast-host

- type: DOM element selected by `document.getElementById("toasts")`
- default: present in the dashboard shell as `<div id="toasts"></div>`
- required: true
- meaning: append target for every generated toast; absence causes the helper call to fail before any removal timer is scheduled.

### field-variant

- type: string passed by the caller and appended to the base `toast` class
- default: none at helper level; first-party callers pass `blocked` or `ok`
- required: true
- meaning: controls the toast's variant class and therefore its left-accent styling; the helper performs no whitelist validation.

### field-title-text

- type: string-like value assigned to `.t-title.textContent`
- default: none at helper level
- required: true
- meaning: short visible toast heading; first-party blocked toasts use `⛔ worker blocked`, and answer-success toasts use `✓ answer sent`.

### field-body-text

- type: optional string-like value assigned to `.t-body.textContent` only when truthy
- default: no body node when omitted, empty, null, undefined, or otherwise falsey
- required: false
- meaning: longer visible toast message; blocked toasts use the blocked-event detail or fallback text, while answer-success toasts intentionally omit it.

### field-ttl

- type: number-like millisecond delay passed to `setTimeout`
- default: 7000 when the caller passes a falsey value
- required: false
- meaning: controls when the generated toast removes itself from the DOM; first-party blocked toasts pass 7000 and answer-success toasts pass 3500.

### field-toast-dom

- type: transient DOM subtree rooted at `div.toast.<variant>`
- default: none before an event calls the helper
- required: false
- meaning: one generated toast card containing exactly one `.t-title` child and, only when `bodyText` is truthy, one `.t-body` child after the title.

## Methods

### method-push-toast

- sig: `pushToast(variant, titleText, bodyText, ttl) -> void`
- abstract: false
- raises: none intentionally caught or transformed by groom.
- code: groom/groom/templates/dashboard.html::pushToast
- step: Create one `div` element for the toast root.
- step: Set the root class string to `toast ` followed by the caller-supplied variant.
- step: Create one title `div`, set its class to `t-title`, assign `titleText` through `textContent`, and append it to the toast root.
- step: If `bodyText` is truthy, create one body `div`, set its class to `t-body`, assign `bodyText` through `textContent`, and append it after the title.
- step: Append the toast root to the dashboard `#toasts` host.
- step: Schedule a timer that removes this toast root after `ttl || 7000` milliseconds.
- step: Do not return the toast node, store it in dashboard state, expose a close action, announce it through an ARIA live region, or synchronize it with server state.

### method-handle-blocked-event-toast

- sig: `groom:blocked CustomEvent -> blocked toast`
- abstract: false
- raises: none intentionally caught or transformed by groom.
- code: groom/groom/templates/dashboard.html::document.body.addEventListener("groom:blocked")
- step: Receive a `groom:blocked` CustomEvent on `document.body` after browser execution of a blocked notification script fragment.
- step: Compute the visible body as `evt.detail || "A workflow needs your input."`.
- step: Call `pushToast("blocked", "⛔ worker blocked", body, 7000)` before any optional system-notification check.
- step: Leave the in-page toast unconditional with respect to `window.Notification` support and `Notification.permission` value.
- step: Continue to the separate browser-notification permission check, which may create a system notification but does not change the in-page toast that was already appended.

### method-handle-answered-event-toast

- sig: `groom:answered CustomEvent -> success toast`
- abstract: false
- raises: none intentionally caught or transformed by groom.
- code: groom/groom/templates/dashboard.html::document.body.addEventListener("groom:answered")
- step: Receive a `groom:answered` CustomEvent on `document.body` after browser execution of a groom answered script fragment.
- step: Call `pushToast("ok", "✓ answer sent", "", 3500)` to append a success toast with no body node.
- step: Read `evt.detail || {}` for the separate selected-worker refresh behavior.
- step: If `detail.id` exists and equals the dashboard's selected worker id, reselect the worker to fetch updated worker detail; otherwise leave the detail pane unchanged.
- step: Do not include the gate file path, submitted answer text, answer result message, or answer log entry in the success toast.
