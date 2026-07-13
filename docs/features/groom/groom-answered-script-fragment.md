---
type: format
slug: groom-answered-script-fragment
title: Groom answered script fragment
---
# Groom answered script fragment

Groom answered script fragment, also the answered notification script fragment, is the transient inline HTML script produced by the [answered notification script renderer](concepts/answered-notification-script-renderer.md) and appended to successful answer broadcasts from [WS /ws](http/groom.md#websocket-dashboard). Browser execution of the fragment dispatches `groom:answered` on `document.body` with a [groom answered browser event detail](groom-answered-browser-event-detail.md), letting the [groom dashboard](gui/screens/groom-dashboard.md) show the answer-success toast and refresh the selected worker detail pane when the answered worker is still selected.

- file: not an on-disk artifact; this is a transient HTML script fragment embedded in a websocket/htmx swap batch.
- code: groom/groom/render.py::render_answered_script
- verify: groom/tests/test_render.py::test_render_answered_script_carries_worker_and_file
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch

## Contract

- producer: [answered notification script renderer](concepts/answered-notification-script-renderer.md) serializes the fragment from one successful answer's workflow container id and gate file path.
- consumer: dashboard websocket swaps and htmx inline-script execution consume the fragment; dashboard JavaScript listens for the resulting `groom:answered` event.
- media: HTML fragment text containing one inline `<script>` element, not JSON, not a full HTML document, and not a websocket frame envelope.
- root count: exactly one top-level `<script>` element.
- return type: Python `str` containing the complete fragment text.
- execution timing: same swapped-content batch as the answered dashboard shell update; it is appended after the shell fragment so the shell refresh and answer-success event travel together.
- source grammar: `<script>document.body.dispatchEvent(new CustomEvent('groom:answered',{detail:` followed by the JSON-serialized detail object and then `}));</script>`.
- lexical shape: no attributes on the script element, no newline, no body text before or after the JavaScript statement, and no extra whitespace outside the JSON-serialized detail object.
- concatenation boundary: the fragment is self-contained and may be concatenated directly after a dashboard shell fragment or other complete HTML fragment without a separator; its closing `</script>` tag terminates the whole payload it owns.
- event target: `document.body`.
- event type: `groom:answered`.
- event detail: a [groom answered browser event detail](groom-answered-browser-event-detail.md) object with exactly `id` and `file_path` keys.
- detail key order: the first-party renderer emits `id` before `file_path` because it serializes that two-key object literal; consumers address keys by name and do not require ordering.
- value acceptance: both renderer inputs are required string arguments and may be empty strings; this format performs no semantic validation of workflow existence, gate existence, or answer success.
- placement: [WS /ws](http/groom.md#websocket-dashboard) appends this fragment only after [answer result](answer-result.md) reports `ok=true`; failed, rejected, duplicate, stale, or missing-gate answer attempts broadcast a shell update without this fragment.
- escaping: both detail values are encoded as JSON string values before insertion into script source, so quotes, backslashes, newlines, and markup remain event data rather than executable JavaScript syntax.
- browser execution: htmx inline-script execution runs the statement as script source in the swapped websocket batch; the fragment has no separate parser-visible payload or acknowledgement body.
- replay behavior: each browser execution dispatches exactly one `groom:answered` event; the fragment carries no idempotency token, delivery acknowledgement, retry marker, or duplicate-suppression guard.
- browser prerequisites: execution assumes a browser context where `document.body`, `CustomEvent`, and `dispatchEvent` are available; the fragment itself provides no fallback markup or polyfill.
- excluded content: dashboard shell HTML, worker detail HTML, answer text, gate question, answer success flag, answer result message, answer log entry, browser notification requests, sidecar frames, and HTTP JSON responses are outside this format.
- state mutation: rendering this fragment is pure string production; workflow containers, gates, gate files, answer logs, websocket queues, Docker state, sidecar state, browser DOM state, and browser notification permission are not mutated by the renderer.
- exception model: no exception is intentionally raised for valid string inputs; JSON serialization of the two strings is the only operation that can fail outside first-party input types.
- deeper calls: no first-party groom symbol is called by the renderer; the only delegated operation is standard-library JSON serialization.

## Inputs

### field: container-id-input

- type: `str`
- default: none
- required: true
- meaning: workflow container id to encode as `event.detail.id`.

### field: file-path-input

- type: `str`
- default: none
- required: true
- meaning: gate context-file path to encode as `event.detail.file_path`.

## Output

### field: return-value

- type: `str` containing one inline `<script>` element.
- default: none
- required: true
- meaning: complete fragment appended to a successful answer broadcast after the refreshed dashboard shell fragment.

## Fields

### field-script-element

- type: HTML `<script>` element
- default: none
- required: true
- meaning: the only root element in the fragment; its text dispatches the answered CustomEvent on the dashboard document body.

### field-script-source

- type: JavaScript statement text inside the root `<script>` element
- default: none
- required: true
- meaning: exact single statement `document.body.dispatchEvent(new CustomEvent('groom:answered',{detail:<detail>}));`, where `<detail>` is the JSON-serialized detail object.

### field-dispatch-target

- type: JavaScript expression
- default: `document.body`
- required: true
- meaning: DOM event target used by dashboard listeners for answered-gate success notifications.

### field-event-name

- type: JavaScript string literal
- default: `"groom:answered"`
- required: true
- meaning: fixed CustomEvent type that identifies successful gate-answer notifications to dashboard JavaScript.

### field-custom-event-init

- type: JavaScript object expression
- default: none
- required: true
- meaning: CustomEvent initialization object with exactly one first-party property, `detail`, whose value is the serialized [groom answered browser event detail](groom-answered-browser-event-detail.md).

### field-detail

- type: JSON-serialized object value inside the CustomEvent init object
- default: none
- required: true
- producer-inputs: `container_id` and `file_path` arguments supplied to `render_answered_script`.
- consumer-use: read by the dashboard `groom:answered` listener as `event.detail` after browser execution.
- meaning: two-key [groom answered browser event detail](groom-answered-browser-event-detail.md) object describing the workflow and gate that accepted an answer.

### field-detail-id

- type: JSON string value
- default: none in first-party produced fragments
- required: true in first-party produced fragments
- wire-key: `id`
- producer-input: `container_id` argument supplied to `render_answered_script`.
- consumer-use: dashboard JavaScript compares this value to the currently selected worker id before refreshing worker detail.
- meaning: workflow container id copied from the successful answer command and used by the dashboard listener to decide whether the currently selected worker detail should be refreshed.

### field-detail-file-path

- type: JSON string value
- default: none in first-party produced fragments
- required: true in first-party produced fragments
- wire-key: `file_path`
- producer-input: `file_path` argument supplied to `render_answered_script`.
- consumer-use: preserved in the browser event detail for observers and tests; the current dashboard success listener does not branch on it.
- meaning: gate context-file path copied from the successful answer command and preserved in the browser event detail for observers and tests.
