---
type: format
slug: dashboard-websocket-answer-frame
title: Dashboard websocket answer frame
---
# Dashboard websocket answer frame

Dashboard websocket answer frame is the JSON object sent by the [groom dashboard](gui/screens/groom-dashboard.md) answer form over [WS /ws](http/groom.md#websocket-dashboard). This is the dashboard answer command payload (`dashboard-answer-command`): it is rendered by the [worker detail renderer](concepts/worker-detail-renderer.md#render-answer-form), consumed by the [run dashboard websocket session](http/groom.md#run-dashboard-websocket-session), and delegated to the [gate-answering layer](concepts/gate-answering-layer.md) to apply one operator answer to one open [gate info](concepts/gate-info.md) on one [workflow container](concepts/workflow-container.md). The handled frame yields an [answer result](answer-result.md), records one [answer log entry](answer-log-entry.md) for every attempted answer, broadcasts a refreshed [dashboard shell fragment](dashboard-shell-fragment.md), and successful answers append a [groom answered script fragment](groom-answered-script-fragment.md).

- file: not an on-disk artifact; this is one browser websocket JSON message produced by an htmx `ws-send` form.
- code: groom/groom/app.py::_handle_command
- code: groom/groom/render.py::_answer_form
- verify: groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch

## Contract

- shape: JSON object with four first-party submitted keys: `cmd`, `workflow_id`, `file_path`, and `answer`; no envelope, version key, request id, timestamp, correlation id, or reply address is present.
- transport: one browser-to-server websocket text message decoded as JSON by the dashboard websocket receive loop and handled in-process; the command handler does not itself parse JSON bytes or emit a reply frame.
- producer: each open gate block in the worker detail pane renders one `<form class="answer" ws-send>` with hidden `cmd`, hidden `workflow_id`, hidden `file_path`, and textarea `answer` controls; htmx's websocket extension serializes the submitted controls into this JSON object.
- consumer: the [dashboard websocket receive loop](concepts/dashboard-websocket-receive-loop.md) receives one decoded JSON value per websocket message and passes it to `_handle_command`; the command handler's contract is an object with `.get(...)` lookup semantics, and this format defines no recovery payload for malformed JSON or non-object values.
- command guard: only frames whose `cmd` value is exactly `"answer"` are handled; every other command value or an absent `cmd` is ignored with no state change, log entry, gate write, broadcast, or acknowledgement frame.
- acceptance boundary: a handled answer command does not perform schema validation beyond the command guard; it string-normalizes the target and answer fields and delegates semantic validity to the gate-answering layer.
- normalization: handled frames read `workflow_id`, `file_path`, and `answer` with object lookup defaults of `""`, convert each resolved value with `str(value)`, and pass the normalized strings to the [gate-answering layer](concepts/gate-answering-layer.md).
- workspace lookup: after normalizing `workflow_id`, the handler reads the process-local [workflow registry](concepts/workflow-registry.md) for that id; a present workflow contributes its current `workspace_volume`, while an absent workflow or empty volume still calls the gate-answering layer with `workspace_volume=""` so the result reports the domain failure.
- gate-answer call: the handler calls `answer_gate(container_id, file_path, answer, workspace_volume=workspace_volume)` exactly once for each handled answer frame before logging, state transition, shell rendering, answered-script rendering, or broadcast.
- log effect: after the gate-answering call returns, the handler builds exactly one [answer log entry](answer-log-entry.md) with `event="answer"`, the normalized `container_id`, normalized `file_path`, and the returned `ok` and `message`, then appends it to the process-local [answer event log](concepts/answer-event-log.md).
- state effect: when the answer result is successful, the workflow was found before the answer attempt, that workflow now has no gates, and its [workflow state](concepts/workflow-state.md) is `blocked`, the handler changes that workflow state to `running` before rendering the broadcast shell; all other combinations leave workflow state unchanged at this layer.
- target scope: `workflow_id` selects the workflow registry entry used to find the current workspace volume, and `file_path` selects the gate context file within that workflow; multiple simultaneous gates remain unambiguous because the form submits both values.
- serialization: the browser sends exactly the submitted form-control names as JSON object keys; the first-party form emits all four keys while its controls are enabled, field order is not meaningful, and duplicate form names are not produced by the first-party form.
- response model: the server sends no direct acknowledgement frame for this message. Every attempted answer records an [answer log entry](answer-log-entry.md), broadcasts a refreshed [dashboard shell fragment](dashboard-shell-fragment.md), and uses the [answer result](answer-result.md) to decide whether successful answers additionally append a [groom answered script fragment](groom-answered-script-fragment.md) whose [browser event detail](groom-answered-browser-event-detail.md) carries the answered workflow id and file path.
- broadcast ordering: the refreshed shell fragment is rendered after the answer log append and any successful last-gate state transition; the answered script, when present, is concatenated after that shell fragment in the same broadcast payload.
- failure model: blank or stale identifiers, already-consumed gates, missing workspace volume, write failures, and other gate-answering failures are represented by the [answer result](answer-result.md); failures still trigger a shell broadcast but do not dispatch `groom:answered` and do not clear the visible gate through the success handler.
- exception model: unexpected exceptions from the gate-answering call, log append, shell rendering, answered-script rendering, or broadcast are not converted into an acknowledgement or failure frame by this command format; completed earlier side effects are not rolled back.
- ignored data: fields other than `cmd`, `workflow_id`, `file_path`, and `answer` are ignored by the command handler.

## Fields

### field-cmd

- type: string JSON value emitted by the first-party form; any JSON value is accepted by the handler for comparison.
- default: absent
- required: true for the first-party answer command; required for handling because any value other than exact string `"answer"`, including an absent value, is ignored.
- wire-key: `cmd`
- producer-control: hidden input `name="cmd" value="answer"`.
- consumer-use: command discriminator checked before any workflow lookup, gate-answering call, log entry, or broadcast.
- meaning: command discriminator copied from hidden input `name="cmd" value="answer"`; it is the only command recognized by the dashboard websocket command handler.

### field-workflow_id

- type: string-convertible JSON value
- default: `""`
- required: true for a successful gate answer; missing or blank values are still normalized and delegated to the gate-answering layer, which returns the failure result.
- wire-key: `workflow_id`
- producer-control: hidden input `name="workflow_id"` rendered from the selected workflow container id.
- consumer-use: converted with `str(value)`, used as the in-memory workflow registry key, copied to the gate-answering call as `container_id`, copied into the answer log entry, and included in the success-only answered browser event detail.
- meaning: workflow container id copied from the selected worker detail form's hidden `workflow_id` input; the handler converts it to text and uses it to look up the current workflow and workspace volume before attempting the gate write. The form value is escaped when rendered from the selected workflow container id and is not truncated by this command handler.

### field-file_path

- type: string-convertible JSON value
- default: `""`
- required: true for a successful gate answer; missing or blank values are still normalized and delegated to the gate-answering layer, which returns the failure result.
- wire-key: `file_path`
- producer-control: hidden input `name="file_path"` rendered from the open gate's context-file path.
- consumer-use: converted with `str(value)`, copied to the gate-answering call as the target gate path, copied into the answer log entry, and included in the success-only answered browser event detail.
- meaning: gate context-file path copied from the selected gate block's hidden `file_path` input; the handler converts it to text and passes it as the gate file to answer. The value scopes the answer to one gate when the selected workflow has multiple open gates.

### field-answer

- type: string-convertible JSON value
- default: `""`
- required: false
- wire-key: `answer`
- producer-control: textarea `name="answer"` rendered in the selected worker detail answer form.
- consumer-use: converted with `str(value)` and passed only to the gate-answering layer; it is not copied into the answer log entry, dashboard shell broadcast, or `groom:answered` browser event detail.
- meaning: operator-authored answer copied from the multiline `answer` textarea. Blank answers are not blocked by the dashboard client or websocket command handler; the gate-answering layer receives the normalized string and decides the resulting gate-file update.
