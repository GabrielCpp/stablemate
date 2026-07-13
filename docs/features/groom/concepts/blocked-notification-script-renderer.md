---
type: concept
slug: blocked-notification-script-renderer
title: Blocked notification script renderer
---
# Blocked notification script renderer

Blocked notification script renderer is the groom render-layer function that turns one server-chosen message string into a [blocked notification script fragment](../blocked-notification-script-fragment.md). The [receive blocked push](../http/groom.md#receive-blocked-push) invocation and [sidecar blocked applier](sidecar-blocked-applier.md) append this script after a [dashboard shell fragment](../dashboard-shell-fragment.md) so the [groom dashboard](../gui/screens/groom-dashboard.md) receives a `groom:blocked` browser event without changing the shell fragment shape; [browser notification permission](browser-notification-permission.md) decides whether that event also becomes a system notification.

- code: groom/groom/render.py::render_notify_script

## Contract

- purpose: serialize one blocked-gate notification message as a same-swap-batch script that dispatches `groom:blocked` on `document.body`.
- input: caller supplies the complete operator-facing message string; this renderer does not truncate, format, or look up workflow or gate state.
- output: exactly one [blocked notification script fragment](../blocked-notification-script-fragment.md) string.
- source grammar: `<script>document.body.dispatchEvent(new CustomEvent('groom:blocked',{detail:` followed by the JSON-serialized message string and then `}));</script>`.
- lexical shape: one root `<script>` element with no attributes, no leading or trailing text, no newline, and no extra whitespace outside the serialized message value.
- event name: fixed `groom:blocked` CustomEvent type.
- event target: fixed `document.body` dispatch target.
- event detail: the supplied message string, JSON-serialized as the CustomEvent `detail` value.
- placement: callers append the returned script after the out-of-band shell fragment only when a new blocked-gate notification should fire.
- exclusions: no dashboard shell HTML, inbox rows, status-bar markup, answer-result script, websocket frame envelope, HTTP response body, or JSON API response is included.
- state mutation: rendering does not mutate workflow containers, gate records, browser notification permission, websocket queues, sidecar connections, Docker state, answer files, or gate files.
- escaping: the message is encoded as a JavaScript string value by JSON serialization, so quotes, backslashes, newlines, and markup characters in the message remain data inside `event.detail` rather than script syntax.
- serialization defaults: JSON serialization uses the standard string encoder defaults, so non-ASCII characters are emitted as JSON escape sequences rather than literal Unicode characters in the script source.
- HTML embedding boundary: the renderer does not HTML-escape the serialized string or neutralize script end-tag text before placing it inside raw `<script>` content; callers treat the message as notification text, not trusted HTML.

## Fields

### field-message

- type: `str`
- default: none
- required: true
- meaning: operator-facing blocked-gate message to expose as the `detail` string on the dashboard `groom:blocked` event.

### field-script-fragment

- type: [blocked notification script fragment](../blocked-notification-script-fragment.md)
- default: none
- required: true
- meaning: inline script fragment that htmx executes when it arrives in swapped websocket or HTTP content.

### field-script-prefix

- type: literal string
- default: `<script>document.body.dispatchEvent(new CustomEvent('groom:blocked',{detail:`
- required: true
- meaning: fixed opening source emitted before the serialized message value; it chooses the document-body dispatch target, the CustomEvent constructor, and the blocked event name.

### field-serialized-detail

- type: JSON string value
- default: none
- required: true
- meaning: JSON serialization of the supplied message with standard string-encoder defaults, embedded directly as the `detail` property value in the CustomEvent initialization object.

### field-script-suffix

- type: literal string
- default: `}));</script>`
- required: true
- meaning: fixed closing source emitted after the serialized message value; it closes the event initialization object, dispatch call, script statement, and script element.

## Methods

### method-render-notify-script

- sig: `render_notify_script(message: str) -> str`
- abstract: false
- raises: none intentionally raised for an empty or non-empty string message.
- code: groom/groom/render.py::render_notify_script

Builds the dashboard blocked-event script from one already-composed message. The method serializes only the message value, embeds it as `CustomEvent('groom:blocked', {detail: ...})`, and returns the script text for the caller to concatenate with the dashboard shell update.

#### Effects

- Reads: the supplied message string.
- Serializes: the message with JSON string escaping for safe embedding in JavaScript source.
- Preserves: the message only as a JavaScript string value; the renderer does not perform HTML sanitization, HTML escaping, markdown rendering, or notification-body fallback selection.
- Concatenates: the fixed script prefix, serialized detail value, and fixed script suffix into one fragment string.
- Emits: one [blocked notification script fragment](../blocked-notification-script-fragment.md) that dispatches `groom:blocked` on `document.body` when executed by the browser.
- Calls: no first-party groom helper; the only delegated operation is standard-library JSON serialization.
- Does not mutate: workflow containers, open gates, registry membership, scanning state, websocket queues, browser DOM state, browser permission state, sidecar state, Docker state, answer logs, answer files, or gate files.

## Algorithms

### algorithm-render-blocked-notification-script

- step: Receive the already-composed notification message from the caller.
- step: Serialize that message as a JSON string value so it can be inserted into JavaScript source as data.
- step: Build a single inline script whose only statement dispatches `new CustomEvent('groom:blocked', {detail: <serialized-message>})` on `document.body`.
- step: Return the script text without executing it, wrapping it in a websocket frame, or attaching it to any shell fragment.

## Failure Semantics

- The renderer intentionally raises no groom-specific exception for empty or non-empty string messages.
- Serialization failures are not converted into a renderer-specific result; if the supplied value cannot be serialized by the underlying JSON serializer, the exception propagates to the caller.
- Empty messages are valid and produce a `groom:blocked` event whose `detail` value is the empty string; downstream dashboard behavior owns any fallback display text.
- If the serialized message text causes the browser's HTML parser to terminate the script element early, this renderer has no recovery path; it returns raw script text and does not validate browser parseability beyond JavaScript string serialization.
- Rendering success means only that the script string was produced; it does not prove browser receipt, htmx execution, notification permission, toast display, or system notification creation.
