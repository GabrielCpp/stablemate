---
type: concept
slug: dashboard-toast-pusher
title: Dashboard toast pusher
---
# Dashboard toast pusher

Dashboard toast pusher is the groom dashboard's in-page notification helper. It appends transient toast DOM nodes to the [groom dashboard](../gui/screens/groom-dashboard.md) `#toasts` host when the client module receives a `notify` or `answered` JSON frame over the [dashboard websocket receive loop](dashboard-websocket-receive-loop.md)'s peer — the browser socket — and when a command the client tried to send had no socket to travel on. [Browser notification permission](browser-notification-permission.md) only gates the optional system notification and never gates these in-page toasts.

It is a client-side unit. The server no longer renders script fragments that dispatch DOM CustomEvents; it pushes JSON, and the frame dispatcher in the client module calls this helper directly.

- code: groom/groom/assets/dashboard.js::pushToast
- code: groom/groom/assets/dashboard.js::onNotify
- code: groom/groom/assets/dashboard.js::onAnswered
- code: groom/groom/assets/dashboard.css::#toasts,.toast

## Contract

- purpose: show short-lived, page-local confirmation or blocked-work notifications without changing server state, browser route, selected run, selected repository, websocket connection, or notification permission.
- trigger model: the helper is called from ordinary module functions — `onNotify`, `onAnswered`, and the answer-form submit handler — which the socket frame dispatcher invokes by frame `type`. No CustomEvent, no server-rendered script, and no `document.body` listener is involved.
- host: every toast is appended to the existing `#toasts` element at the end of the dashboard body.
- ordering: newer toasts are appended after older toasts in DOM order; the CSS host stacks them as a fixed vertical column.
- lifetime: each toast schedules its own removal with `setTimeout`; no shared queue, cancellation, deduplication, persistence, or maximum-count trimming exists.
- content safety: title and body values are assigned through `textContent`, so markup-like message text is displayed as text rather than interpreted as HTML.
- notify frame behavior: a `{"type": "notify", "message": …}` frame always pushes one `blocked` toast titled `⛔ worker blocked` with the frame's message or fallback body `A workflow needs your input.` and a 7000 ms lifetime, independent of Notification API availability or permission state.
- answered frame behavior: a `{"type": "answered", …}` frame always pushes one `ok` toast titled `✓ answer sent`, omits a body node, and uses a 3500 ms lifetime. It does not refresh the detail pane: the same server command that produced the frame also pushed a `detail` frame to the tabs watching that run, so the pane is already current.
- send-failure behavior: when `sendCommand` reports that there was no open socket, the answer-form handler pushes one `blocked` toast titled `✗ not sent` with a 7000 ms lifetime and leaves the operator's typed answer in the textarea.
- visual placement: the toast host is fixed at the lower-right of the viewport with a high z-index; individual toasts are 300 px wide cards with a dark background, border, left accent stripe, small title, optional single-line body, shadow, and slide-in animation.
- variant styling: the default/blocked toast uses the blocked accent color; the `ok` variant overrides only the left accent stripe with the running/success color.
- announcement: the `#toasts` host itself carries `role="alert"` and `aria-live="assertive"` in the shell, so a toast inserted into it is announced without the generated nodes needing roles of their own. Individual toasts still have no focus movement, no keyboard interaction, and no close control.
- error handling: missing `#toasts`, DOM append failures, invalid timeout values, and timer failures are not caught or transformed by groom.
- excluded effects: the helper does not create system browser notifications, request Notification permission, send HTTP requests, send websocket messages, mutate workflow containers, mutate gate records, update the client store, refresh run detail, or navigate.

## Fields

### field-toast-host

- type: DOM element selected by `document.getElementById("toasts")`
- default: present in the dashboard shell as `<div id="toasts" role="alert" aria-live="assertive"></div>`
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
- meaning: short visible toast heading; first-party blocked toasts use `⛔ worker blocked`, answer-success toasts use `✓ answer sent`, and a failed send uses `✗ not sent`.

### field-body-text

- type: optional string-like value assigned to `.t-body.textContent` only when truthy
- default: no body node when omitted, empty, null, undefined, or otherwise falsey
- required: false
- meaning: longer visible toast message; blocked toasts use the `notify` frame's message or fallback text, a failed send explains that the answer is still in the box, and answer-success toasts intentionally omit it.

### field-ttl

- type: number-like millisecond delay passed to `setTimeout`
- default: 7000 when the caller passes a falsey value
- required: false
- meaning: controls when the generated toast removes itself from the DOM; first-party blocked and failed-send toasts pass 7000 and answer-success toasts pass 3500.

### field-toast-dom

- type: transient DOM subtree rooted at `div.toast.<variant>`
- default: none before a frame or a failed send calls the helper
- required: false
- meaning: one generated toast card containing exactly one `.t-title` child and, only when `bodyText` is truthy, one `.t-body` child after the title.

## Methods

### method-push-toast

- sig: `pushToast(variant, titleText, bodyText, ttl) -> void`
- abstract: false
- raises: none intentionally caught or transformed by groom.
- code: groom/groom/assets/dashboard.js::pushToast
- step: Create one `div` element for the toast root.
- step: Set the root class string to `toast ` followed by the caller-supplied variant.
- step: Create one title `div`, set its class to `t-title`, assign `titleText` through `textContent`, and append it to the toast root.
- step: If `bodyText` is truthy, create one body `div`, set its class to `t-body`, assign `bodyText` through `textContent`, and append it after the title.
- step: Append the toast root to the dashboard `#toasts` host.
- step: Schedule a timer that removes this toast root after `ttl || 7000` milliseconds.
- step: Do not return the toast node, store it in the client store, expose a close action, or synchronize it with server state.

### method-on-notify

- sig: `onNotify(message) -> void`
- abstract: false
- raises: none intentionally caught or transformed by groom.
- code: groom/groom/assets/dashboard.js::onNotify
- step: Receive the `message` string carried by a `{"type": "notify"}` frame, dispatched by the socket frame handler.
- step: Compute the visible body as `message || "A workflow needs your input."`.
- step: Call `pushToast("blocked", "⛔ worker blocked", body, 7000)` before any optional system-notification check.
- step: Leave the in-page toast unconditional with respect to `window.Notification` support and `Notification.permission` value.
- step: Continue to the separate browser-notification permission check, which may create a system notification but does not change the in-page toast that was already appended.

### method-on-answered

- sig: `onAnswered() -> void`
- abstract: false
- raises: none intentionally caught or transformed by groom.
- code: groom/groom/assets/dashboard.js::onAnswered
- step: Receive a `{"type": "answered", "id": …, "file_path": …}` frame, dispatched by the socket frame handler to every connected tab.
- step: Call `pushToast("ok", "✓ answer sent", "", 3500)` to append a success toast with no body node.
- step: Do not read the frame's `id` or `file_path`, do not compare them to this tab's selection, and do not re-fetch run detail — the accompanying `detail` push has already refreshed the pane for the tabs that have that run open.
- step: Do not include the gate file path, submitted answer text, answer result message, or answer log entry in the success toast.
