---
type: concept
slug: browser-notification-permission
title: Browser notification permission
---
# Browser notification permission

Browser notification permission is browser-owned state requested by the dashboard's [enable browser notifications from settings](../gui/screens/groom-dashboard.md#enable-browser-notifications-from-settings) interaction and the dashboard's one-time first-click bootstrap, then consumed when a [dashboard notify message](../dashboard-notify-message.md) arrives on the socket after a [blocked push payload](../blocked-push-payload.md), a [sidecar blocked applier](sidecar-blocked-applier.md) delta, or a fired alert rule records the event. It gates only system-level browser notifications for the [groom dashboard](../gui/screens/groom-dashboard.md); the in-page [dashboard toast pusher](dashboard-toast-pusher.md) remains available without this permission.

- code: groom/groom/assets/dashboard.js::wireEvents
- code: groom/groom/assets/dashboard.js::onNotify

## Contract

- owner: the browser owns the permission prompt, stored permission value, repeat-request behavior, denied-state recovery, and persistence; groom only calls the Notification API from dashboard click handling and later reads the exposed permission value before creating a system notification.
- availability guard: every groom access to the Notification API first checks that `"Notification" in window`; browsers without the API never receive a permission request and never create a system notification.
- first-click request path: when the dashboard script loads and the browser reports both Notification API availability and `Notification.permission === "default"`, groom registers one body click listener that calls `Notification.requestPermission()` on the first body click and then removes itself.
- settings request path: the settings `Enable notifications` button asks for permission on activation when `window.Notification` exists; the delegated handler requires the event target itself to have `id="btn-notify"`.
- double-request edge: if the first eligible body click is the settings button activation while permission is still `default`, the one-time first-click listener may call `Notification.requestPermission()` before the delegated settings branch calls it again because the first-click listener is registered before the delegated body-click handler.
- granted behavior: when a later [dashboard notify message](../dashboard-notify-message.md) arrives and `Notification.permission === "granted"`, the dashboard creates one browser notification titled `groom: workflow blocked` with the frame's `message` string, or the fallback text, as the notification body.
- fallback behavior: when permission is `default`, `denied`, unavailable, or otherwise not `granted`, the same frame still creates the in-page blocked toast and no system notification is created.
- local state: the dashboard does not mirror the permission value into application state, local storage, server state, websocket messages, CSS classes, or visible button state.
- operator feedback: the settings request does not read the returned permission value, disable the button, change its label, add busy state, change focus, or show a success/failure toast after the browser permission flow resolves.
- error handling: groom does not catch errors from `Notification.requestPermission()` or `new Notification(...)`; the in-page blocked toast is pushed before system-notification construction on every notify frame.
- server boundary: notification permission never changes workflow state, gate records, blocked-push handling, sidecar blocked handling, answer handling, status counts, or websocket broadcasts. It is browser-side only: the server sends the identical notify frame to every tab and never learns which of them raised a system notification.

## Fields

### notification-api-available

- type: boolean browser capability check expressed as `"Notification" in window`
- default: browser-dependent
- required: false
- meaning: true allows groom to call `Notification.requestPermission()` and later construct system notifications; false disables all permission requests and system notifications while leaving dashboard toasts intact.

### permission-default

- type: browser `Notification.permission` string value
- default: browser-dependent; commonly the initial value before the operator has granted or denied permission for the origin
- required: false
- meaning: permission has not been decided for the origin; the first body click and the settings button are allowed to request permission, and blocked events do not create system notifications until the browser reports `granted`.

### permission-granted

- type: browser `Notification.permission` string value
- default: none
- required: false
- meaning: permission is allowed for the origin; future blocked events may create system notifications in addition to in-page toasts.

### permission-denied

- type: browser `Notification.permission` string value
- default: none
- required: false
- meaning: permission is blocked for the origin; settings activation still calls the request API when available, but blocked events continue without system notifications unless the browser state later changes outside groom.

### first-click-request-listener

- type: one-time browser click listener on `document.body`
- default: absent unless the dashboard loads with Notification API availability and permission `default`
- required: false
- meaning: opportunistically requests permission once on the first body click of the page session and removes itself immediately after it calls the browser request API.

### settings-request-trigger

- type: native button activation of `#btn-notify`
- default: present in the settings pane while the dashboard shell is loaded
- required: true
- meaning: explicit operator control that calls the browser permission request API when the Notification API is available; it has no granted, denied, busy, or unavailable visual state in groom.

### notify-frame-system-notification

- type: browser `Notification` object construction attempt
- default: absent for every notify frame unless Notification API exists and permission is `granted`
- required: false
- meaning: optional system notification created from an arriving [dashboard notify message](../dashboard-notify-message.md) after the in-page blocked toast is queued; title is fixed to `groom: workflow blocked` and body is the frame's `message` string or `A workflow needs your input.` when it is empty.

### system-notification-title

- type: literal browser notification title string
- default: `groom: workflow blocked`
- required: true when `notify-frame-system-notification` is created
- meaning: fixed title passed as the first argument to the browser `Notification` constructor for every granted notify-frame notification.

### system-notification-body

- type: browser notification options body string
- default: `A workflow needs your input.` when the notify frame's `message` is empty
- required: true when `notify-frame-system-notification` is created
- meaning: notification body passed as `{ body: body }`; it is the [dashboard notify message](../dashboard-notify-message.md) `message` string when non-empty, otherwise the fallback prompt text.

## Methods

### method-request-permission-on-first-body-click

- sig: `document.body click -> Notification.requestPermission()`
- abstract: false
- raises: none intentionally caught or transformed by groom.
- code: groom/groom/assets/dashboard.js::wireEvents
- step: During dashboard script initialization, check whether the browser exposes `window.Notification` and currently reports `Notification.permission === "default"`.
- step: If either check fails, do not register the one-time listener and do not request permission during initialization.
- step: If both checks pass, register a `document.body` click listener with once-only semantics.
- step: On the first body click, call `Notification.requestPermission()` without arguments and without awaiting or reading the result.
- step: Remove the listener from `document.body` after the request call; the once-only listener option also prevents later invocations.
- step: Leave button labels, focus, DOM state, local storage, server state, websocket state, and workflow state unchanged.

### method-request-permission-from-settings

- sig: `#btn-notify click -> Notification.requestPermission()`
- abstract: false
- raises: none intentionally caught or transformed by groom.
- code: groom/groom/assets/dashboard.js::wireEvents
- step: The one delegated `document.body` click handler resolves repository-picker, tree, refresh, and command-palette targets before it reaches settings-button handling.
- step: If the event target's id is exactly `btn-notify` and the browser exposes `window.Notification`, call `Notification.requestPermission()` without arguments.
- step: Do not read, await, branch on, or display the returned permission value.
- step: If the Notification API is unavailable or the event target is not exactly `#btn-notify`, make no permission request.
- step: Leave selected worker, selected repository, dashboard panes, command palette, status bar, websocket connection, server state, and browser route unchanged.

### method-create-system-notification-for-notify-frame

- sig: `notify frame -> Notification | no-op`
- abstract: false
- raises: none intentionally caught or transformed by groom.
- code: groom/groom/assets/dashboard.js::onNotify
- step: When the frame dispatcher routes a `notify` frame to the notify handler, compute the message body from `msg.message || "A workflow needs your input."`.
- step: Push the in-page blocked toast through the [dashboard toast pusher](dashboard-toast-pusher.md#method-on-notify) independently of Notification API availability or permission state, so the alert is never lost to a permission the operator declined.
- step: Check whether the browser exposes `window.Notification` and currently reports `Notification.permission === "granted"`.
- step: If either check fails, stop without creating a system notification.
- step: If both checks pass, construct one browser notification with title `groom: workflow blocked` and options object `{ body: body }`.
- step: Do not set notification icon, tag, renotify, requireInteraction, click handler, close handler, or server acknowledgement.
