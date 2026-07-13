---
type: format
slug: blocked-notification-script-fragment
title: Blocked notification script fragment
---
# Blocked notification script fragment

Blocked notification script fragment is the transient inline HTML script produced by the [blocked notification script renderer](concepts/blocked-notification-script-renderer.md) and appended to blocked-gate broadcasts from the [groom server](http/groom.md). It dispatches the `groom:blocked` dashboard event consumed by the [groom dashboard](gui/screens/groom-dashboard.md), [browser notification permission](concepts/browser-notification-permission.md), and [dashboard toast pusher](concepts/dashboard-toast-pusher.md) after a [blocked push payload](blocked-push-payload.md) or [sidecar blocked applier](concepts/sidecar-blocked-applier.md) records a gate.

- file: not an on-disk artifact; this is a transient HTML script fragment embedded in a websocket/htmx swap batch.
- code: groom/groom/render.py::render_notify_script

## Contract

- producer: [blocked notification script renderer](concepts/blocked-notification-script-renderer.md) serializes the fragment from one caller-supplied message string.
- renderer input: one required `str` message supplied by the caller; first-party callers build it from workflow display name and a truncated gate question before invoking the renderer.
- consumers: dashboard websocket swaps and htmx inline-script execution consume the fragment; dashboard JavaScript listens for the resulting `groom:blocked` event and passes its detail to the [dashboard toast pusher](concepts/dashboard-toast-pusher.md) before the optional browser Notification check.
- media: HTML fragment text containing one inline `<script>` element, not JSON, not a full HTML document, and not a websocket frame envelope.
- root count: exactly one top-level `<script>` element.
- execution timing: same swapped-content batch as the blocked shell update; it is appended after the shell fragment so the DOM update and event notification travel together.
- source grammar: `<script>document.body.dispatchEvent(new CustomEvent('groom:blocked',{detail:` followed by the JSON-serialized message string and then `}));</script>`.
- lexical shape: no attributes on the script element, no newline, no body text before or after the JavaScript statement, and no extra whitespace outside the JSON-serialized message string.
- event target: `document.body`.
- event type: `groom:blocked`.
- event detail: the caller-provided first-party message string, not an object envelope; the renderer relies on the `str` input contract rather than enforcing a runtime type check.
- placement: [receive blocked push](http/groom.md#receive-blocked-push) and the [sidecar blocked applier](concepts/sidecar-blocked-applier.md) append this fragment only after a non-empty gate file path has been accepted, a workflow has been marked blocked, and the [dashboard shell fragment](dashboard-shell-fragment.md) has been rendered.
- message construction: first-party callers pass the workflow display name after upsert, followed by `": "`, followed by the first 200 characters of the normalized gate question.
- JavaScript escaping: the message is encoded with standard JSON string serialization before insertion into script source, so quotes, backslashes, control characters, and newlines are represented as JavaScript string data inside `event.detail`.
- HTML embedding boundary: the fragment does not HTML-escape `<`, `>`, `&`, or script end-tag text before embedding the serialized value in raw `<script>` content; this format is an event script serializer, not an HTML sanitizer.
- browser behavior: executing the fragment synchronously dispatches one CustomEvent; the dashboard listener derives the toast/system-notification body from `evt.detail || "A workflow needs your input."`, pushes a `blocked` toast titled `⛔ worker blocked` for 7000 ms through the [dashboard toast pusher](concepts/dashboard-toast-pusher.md), and creates a browser notification titled `groom: workflow blocked` only when the browser Notification API exists and permission is `granted`.
- excluded content: inbox/list HTML, status-bar HTML, worker detail panes, repository menu rows, file/diff content, answer-result scripts, sidecar JSON frames, HTTP JSON responses, notification-permission requests, and browser toast DOM nodes are outside this format.
- state mutation: rendering this fragment is pure string production; workflow containers, gates, gate files, answer logs, websocket queues, Docker state, sidecar state, browser DOM state, and browser notification permission are not mutated by the renderer.
- deeper calls: no first-party groom symbol is called by the renderer; the only delegated operation is standard-library JSON serialization.

## Fields

### field-script-element

- type: HTML `<script>` element
- default: none
- required: true
- meaning: the only root element in the fragment; its text dispatches the blocked CustomEvent on the dashboard document body.

### field-script-source

- type: JavaScript statement text inside the root `<script>` element
- default: none
- required: true
- meaning: exact single statement `document.body.dispatchEvent(new CustomEvent('groom:blocked',{detail:<message>}));`, where `<message>` is the JSON-serialized message string.

### field-dispatch-target

- type: JavaScript expression
- default: `document.body`
- required: true
- meaning: the DOM event target used by dashboard listeners for blocked notifications.

### field-event-name

- type: JavaScript string literal
- default: `"groom:blocked"`
- required: true
- meaning: fixed CustomEvent type that identifies blocked-gate notifications to dashboard JavaScript.

### field-custom-event-init

- type: JavaScript object expression
- default: none
- required: true
- meaning: CustomEvent initialization object with exactly one first-party property, `detail`, whose value is the serialized message string.

### field-detail

- type: JSON string value inside the CustomEvent init object
- default: none in first-party produced fragments
- required: true in first-party produced fragments
- meaning: operator-facing notification body; callers choose the text, the renderer preserves it as the `event.detail` string, and the dashboard listener uses it for both the in-page blocked toast body and the optional system notification body.
- serialization: produced by JSON string serialization of the renderer's `message` argument, including escaped quotes, backslashes, control characters, and non-ASCII code points according to the serializer defaults.
- embedding constraint: JSON serialization alone does not neutralize HTML script end tags, so this field must not be described as sanitized HTML content.

## Failure Semantics

- Renderer success means only that the script string was returned; it does not prove websocket delivery, htmx execution, browser event dispatch, toast insertion, Notification API support, notification permission, or operator visibility.
- The produced fragment has no in-band acknowledgement, retry marker, correlation id, timestamp, schema version, or error envelope.
- If the browser does not execute inline scripts from the swap batch, no `groom:blocked` event is dispatched and no fallback DOM element in this fragment reports that failure.
- If the listener receives a falsey `event.detail`, the dashboard uses `A workflow needs your input.` as the toast and system-notification body; this fallback is consumer behavior and is not encoded in the fragment itself.
- If the serialized message causes HTML parser termination of the script element, recovery is outside this format; the renderer performs no HTML-level escaping or validation before returning the fragment.
