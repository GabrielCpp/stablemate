---
type: format
slug: groom-answered-browser-event-detail
title: Groom answered browser event detail
---
# Groom answered browser event detail

Groom answered browser event detail is the JavaScript `CustomEvent.detail` object dispatched on the [groom dashboard](gui/screens/groom-dashboard.md) after a successful [dashboard websocket answer frame](dashboard-websocket-answer-frame.md) is handled by [WS /ws](http/groom.md#websocket-dashboard). The server creates it from the submitted workflow id and gate file path when [answer result](answer-result.md) is successful; the dashboard listener consumes it to show the success toast and, when the answered worker is still the selected worker, refresh that worker detail pane so the answered gate disappears. The [answered notification script renderer](concepts/answered-notification-script-renderer.md) returns a same-swap-batch [groom answered script fragment](groom-answered-script-fragment.md) that carries this detail object; the fragment is appended after the [dashboard shell fragment](dashboard-shell-fragment.md) only on successful answers.

- file: not an on-disk artifact; this is a transient `CustomEvent.detail` object embedded in an inline websocket/htmx [groom answered script fragment](groom-answered-script-fragment.md).
- code: groom/groom/render.py::render_answered_script
- producer: [answered notification script renderer](concepts/answered-notification-script-renderer.md)
- verify: groom/tests/test_render.py::test_render_answered_script_carries_worker_and_file
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch

## Contract

- producer: the dashboard websocket answer handler appends the answered script only when the gate-answering result reports `ok=true`; rejected, duplicate, missing, or failed answers do not produce this detail object or dispatch `groom:answered`.
- event target: `document.body`.
- event name: `groom:answered`.
- event options: the `CustomEvent` initialization object contains only `detail`; the event therefore uses the browser defaults for bubbling, cancellation, and composed-tree crossing.
- media: JavaScript object used as `CustomEvent` detail, serialized into an inline `<script>` by JSON encoding before browser execution; it is not a websocket frame, htmx swap fragment, DOM dataset, form value set, or persisted record.
- shape: exactly two first-party keys, `id` and `file_path`; no command name, answer text, success flag, message, workflow state, gate question, toast text, or websocket frame envelope is included.
- source values: `id` is the normalized `workflow_id` submitted in the answer frame, and `file_path` is the normalized gate file path submitted in the same frame.
- renderer input: `container_id` and `file_path` strings supplied by the dashboard websocket answer command after gate answering succeeds; the renderer does not derive either value from current workflow state, the answer log, or the gate collection.
- renderer output: one [groom answered script fragment](groom-answered-script-fragment.md) that dispatches `new CustomEvent('groom:answered', {detail: {id, file_path}})` on `document.body` when the browser executes the swap batch; the event is dispatched synchronously by that script.
- placement: the websocket command handler concatenates the script after the out-of-band dashboard shell update only when the answer result is successful; failed, duplicate, missing, or rejected answer attempts receive no answered-event script.
- consumer: the dashboard `groom:answered` listener treats a missing or falsey detail as `{}`, always pushes the `answer sent` success toast for the event, and refreshes the selected worker detail only when `detail.id` is truthy and equals the browser's selected worker id.
- scope guarantee: the refresh decision is worker-scoped, not gate-scoped; `file_path` identifies the answered gate for observers and tests but the current first-party browser listener does not branch on it.
- escaping: both fields are JSON-serialized before insertion into script source, so quotes, markup, backslashes, newlines, and non-ASCII characters remain data in `event.detail` instead of JavaScript syntax.
- identity preservation: no trimming, path normalization, id canonicalization, lowercasing, length limiting, or existence check is applied by the detail renderer; the values emitted are the strings supplied to the renderer.
- ordering: object field order is not meaningful; consumers address fields by name.
- excluded content: the answer text, gate question, answer log message, dashboard shell HTML, worker detail HTML, websocket answer command, and sidecar websocket frames are outside this format.
- state mutation: rendering is pure string production; it does not mutate workflow containers, gates, websocket queues, answer logs, sidecar state, Docker state, browser DOM state, or browser notification state.
- deeper calls: no first-party groom symbol is called by the renderer; the only delegated operation is standard-library JSON serialization.

## Inputs

### field-container-id-input

- type: `str`
- default: none
- required: true
- meaning: workflow container id to expose as `detail.id` in the dispatched browser event.

### field-file-path-input

- type: `str`
- default: none
- required: true
- meaning: gate context-file path to expose as `detail.file_path` in the dispatched browser event.

## Output

### field-script-fragment

- type: `str` containing one inline `<script>` element.
- default: none
- required: true
- meaning: [groom answered script fragment](groom-answered-script-fragment.md) that dispatches the `groom:answered` event on `document.body` when executed by the browser.

## Fields

### field-id

- type: JSON string value.
- default: none in the produced event; the browser consumer ignores refresh when the value is absent or falsey.
- required: true in first-party produced events.
- wire-key: `id`
- producer-input: `container_id` argument supplied to `render_answered_script`.
- source: normalized `workflow_id` from the accepted dashboard websocket answer frame.
- consumer-use: dashboard JavaScript compares this value to the selected worker id before refetching worker detail; absent, empty, or non-matching values still allow the success toast but do not trigger the detail refresh.
- meaning: workflow container id whose gate answer succeeded; the dashboard compares it to the currently selected worker id before refetching worker detail.

### field-file_path

- type: JSON string value.
- default: none in the produced event.
- required: true in first-party produced events.
- wire-key: `file_path`
- producer-input: `file_path` argument supplied to `render_answered_script`.
- source: normalized `file_path` from the accepted dashboard websocket answer frame.
- consumer-use: preserved for observers and tests; the current dashboard success listener does not branch on it.
- meaning: gate context-file path answered by the successful command; it preserves the answered gate identity in the event payload even though the current browser refresh condition only reads `id`.
