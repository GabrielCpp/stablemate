---
type: concept
slug: answered-notification-script-renderer
title: Answered notification script renderer
---
# Answered notification script renderer

Answered notification script renderer is the groom render-layer function that turns one successful gate-answer identity into a [groom answered script fragment](../groom-answered-script-fragment.md) carrying the [groom answered browser event detail](../groom-answered-browser-event-detail.md). The [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) handler appends this script after a [dashboard shell fragment](../dashboard-shell-fragment.md) only when [answer result](../answer-result.md) is successful, so the [groom dashboard](../gui/screens/groom-dashboard.md) receives a `groom:answered` browser event without changing the shell fragment shape. This is a leaf groom code concept: after it receives the two strings to serialize, it calls no deeper first-party groom symbol.

- code: groom/groom/render.py::render_answered_script
- verify: groom/tests/test_render.py::test_render_answered_script_carries_worker_and_file
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch

## Contract

- purpose: serialize a successful gate-answer notification as a same-swap-batch script that dispatches `groom:answered` on `document.body`.
- input: caller supplies the answered workflow container id and gate file path; this renderer does not validate the answer result, inspect workflow state, answer a gate, or decide whether the script should be sent.
- output: exactly one [groom answered script fragment](../groom-answered-script-fragment.md) whose browser execution dispatches `new CustomEvent('groom:answered', {detail: {id, file_path}})`.
- return type: Python `str` containing a complete inline `<script>` element.
- root count: exactly one top-level `<script>` element, with no surrounding wrapper, separator, newline, or fallback markup.
- source grammar: `<script>document.body.dispatchEvent(new CustomEvent('groom:answered',{detail:` followed by the JSON-serialized detail object and then `}));</script>`.
- event name: fixed `groom:answered` CustomEvent type.
- event target: fixed `document.body` dispatch target.
- event detail: exactly the supplied container id as `id` and supplied gate path as `file_path`, JSON-serialized as the CustomEvent `detail` object.
- detail key order: the first-party renderer constructs the detail object as `id` followed by `file_path`; consumers use named fields and do not rely on order.
- placement: callers concatenate the returned script after the out-of-band dashboard shell update only on successful answer attempts; rejected, duplicate, missing, and failed answers do not receive this script.
- exclusions: no dashboard shell HTML, worker detail HTML, answer text, gate question, success flag, answer log entry, websocket frame envelope, HTTP response body, sidecar frame, or browser notification request is included.
- state mutation: rendering does not mutate workflow containers, gate records, answer files, gate files, answer logs, websocket queues, browser DOM state, browser notification permission, sidecar state, Docker state, or discovery state.
- escaping: both supplied strings are encoded through JSON serialization before insertion into script source, so quotes, backslashes, newlines, and markup characters remain data inside `event.detail` rather than JavaScript syntax.
- value acceptance: empty strings are accepted as ordinary contract inputs and are serialized without fallback values; the renderer applies no trimming, path normalization, id canonicalization, existence check, or truthiness guard.
- exception model: no exception is intentionally raised for valid string inputs; outside the string contract, ordinary JSON serialization failures propagate to the caller.
- deeper calls: no first-party groom helper is called; the only delegated operation is standard-library JSON serialization.

## Inputs

### field: container-id

- type: `str`
- default: none
- required: true
- meaning: workflow container id to expose as `detail.id` in the dispatched dashboard event.

### field: file-path

- type: `str`
- default: none
- required: true
- meaning: gate context-file path to expose as `detail.file_path` in the dispatched dashboard event.

## Output

### field: script-fragment

- type: `str` containing one inline `<script>` element.
- default: none
- required: true
- meaning: script fragment that htmx executes in the same websocket swap batch as the dashboard shell update.

## Methods

### method-render-answered-script

- sig: `render_answered_script(container_id: str, file_path: str) -> str`
- abstract: false
- raises: none intentionally raised for empty or non-empty string inputs.
- returns: one [groom answered script fragment](../groom-answered-script-fragment.md) string.
- code: groom/groom/render.py::render_answered_script
- verify: groom/tests/test_render.py::test_render_answered_script_carries_worker_and_file
- does:
  - Reads the supplied `container_id` and `file_path` strings without lookup or normalization.
  - Builds a two-key detail object whose `id` value is `container_id` and whose `file_path` value is `file_path`.
  - Serializes the detail object as JSON before embedding it in JavaScript source.
  - Wraps the serialized detail in a single inline script that dispatches `CustomEvent('groom:answered', {detail: ...})` on `document.body`.
  - Returns the script text for the caller to concatenate after a dashboard shell update.
  - Calls no first-party groom helper; standard-library JSON serialization is the bottom of this crawl branch.

Builds the dashboard answered-event script from one workflow id and one gate path. The method serializes only those two values, embeds them as `CustomEvent('groom:answered', {detail: {id, file_path}})`, and returns the script text for the caller to concatenate with the dashboard shell update.
