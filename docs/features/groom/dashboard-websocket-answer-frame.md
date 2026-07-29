---
type: format
slug: dashboard-websocket-answer-frame
title: Dashboard websocket answer frame
---
# Dashboard websocket answer frame

Dashboard websocket answer frame is the JSON object the [groom dashboard](gui/screens/groom-dashboard.md) answer form sends up [WS /ws](http/groom.md#websocket-dashboard). This is the dashboard answer command payload (`dashboard-answer-command`): the browser serializes it, the [dashboard websocket receive loop](concepts/dashboard-websocket-receive-loop.md) decodes it, and the command handler delegates to the [gate-answering layer](concepts/gate-answering-layer.md) to apply one operator answer to one open [gate info](concepts/gate-info.md) on one [workflow container](concepts/workflow-container.md). Every attempted answer yields an [answer result](answer-result.md) and records one [answer log entry](answer-log-entry.md); a successful one additionally pushes an [answered message](dashboard-answered-message.md) back to the tabs.

The socket is the only path for this. Answering is the one browser-to-server write the dashboard performs, and it is deliberately not an HTTP `POST`: the same socket the answer goes up carries the refreshed [run detail](http/groom.md#get-run-detail) back down, so the pane the operator is looking at updates from the write itself rather than from a follow-up fetch the tab has to remember to issue.

- file: not an on-disk artifact; this is one browser-to-server websocket JSON message, serialized by the dashboard module.
- code: groom/groom/app.py::_handle_command
- code: groom/groom/assets/dashboard.js::AnswerForm
- code: groom/groom/assets/dashboard.js::wireAnswerForm
- code: groom/groom/assets/dashboard.js::sendCommand
- refs: [dashboard websocket receive loop](concepts/dashboard-websocket-receive-loop.md), [gate-answering layer](concepts/gate-answering-layer.md), [dashboard client store](concepts/dashboard-client-store.md), [run watch registry](concepts/run-watch-registry.md)
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_an_answered_event
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch

## Contract

- shape: JSON object with four first-party keys: `cmd`, `workflow_id`, `file_path`, and `answer`; no envelope, version key, request id, timestamp, correlation id, or reply address is present.
- transport: one browser-to-server websocket text message decoded as JSON by the dashboard websocket receive loop and handled in-process; the command handler does not itself parse JSON bytes or emit a reply frame.
- producer — form: each open gate block in the run detail pane renders one `<form class="answer" data-answer>` carrying hidden `cmd`, hidden `workflow_id`, hidden `file_path`, and an `answer` textarea. The form is markup only; it has no submit action and no framework binding.
- producer — serialization: one delegated `submit` listener on the document intercepts any `[data-answer]` form, reads its controls with `FormData`, builds a plain object from the control names, and hands it to the socket sender, which serializes it with `JSON.stringify`. No library performs this step; the wire shape is exactly the form's control names.
- send guard: the sender writes only when the socket exists and its `readyState` is `OPEN`, and reports whether it wrote. A refused send raises the *not sent* toast and **leaves the typed answer in the textarea**, so a disconnected tab loses no work and the operator is told, rather than left with an answer that looks accepted and was dropped.
- textarea ownership: the answer textarea is uncontrolled — the renderer never writes its `value` — and the gate block is keyed, so a push re-renders around the same DOM node and a half-typed answer survives it. Only a confirmed send clears the box.
- consumer: the receive loop passes each decoded JSON value to `_handle_command`; the handler's contract is an object with `.get(...)` lookup semantics, and this format defines no recovery payload for malformed JSON or non-object values.
- command guard: only frames whose `cmd` value is exactly `"answer"` are handled by this format. Any other value — including the dashboard's own `watch` command, which the same socket carries — is handled elsewhere or ignored, with no gate write, log entry, state change, or acknowledgement frame from here.
- acceptance boundary: a handled answer command performs no schema validation beyond the command guard; it string-normalizes the target and answer fields and delegates semantic validity to the gate-answering layer.
- normalization: handled frames read `workflow_id`, `file_path`, and `answer` with object lookup defaults of `""`, convert each resolved value with `str(value)`, and pass the normalized strings on.
- workspace lookup: after normalizing `workflow_id`, the handler reads the process-local [workflow registry](concepts/workflow-registry.md) for that id. A present workflow contributes its current `workspace_volume` and its native flag; an absent workflow still calls the gate-answering layer with an empty volume, so the domain failure is reported by the result rather than invented by the handler.
- gate-answer call: the handler calls the gate-answering layer exactly once per handled frame — with the container id, gate path, answer text, workspace volume, and native flag — before logging, state transition, detail push, or broadcast.
- log effect: after the gate-answering call returns, the handler appends exactly one [answer log entry](answer-log-entry.md) with `event="answer"`, the normalized container id and file path, and the returned `ok` and `message`, to the process-local [answer event log](concepts/answer-event-log.md).
- state effect: when the answer succeeded, the workflow was found, that workflow now has no gates, and its [workflow state](concepts/workflow-state.md) is `blocked`, the handler moves that workflow to `running` before the broadcast. Every other combination leaves workflow state unchanged at this layer.
- target scope: `workflow_id` selects the registry entry and therefore the workspace; `file_path` selects the gate context file within it. A workflow with several open gates stays unambiguous because the form submits both.
- response model: the server sends no per-message acknowledgement. A handled answer is observed as a refreshed [dashboard state payload](dashboard-state-payload.md) broadcast to every tab plus this run's detail message to the tabs [watching](concepts/run-watch-registry.md) it; success adds an [answered message](dashboard-answered-message.md) that carries the confirmation toast.
- push ordering: the shell broadcast is sent after the answer log append and after any last-gate state transition; the answered message is sent after that broadcast, and only on success.
- failure model: blank or stale identifiers, already-consumed gates, a missing workspace volume, and write failures are all represented by the [answer result](answer-result.md). Failures still broadcast the shell but send no answered message, so the gate stays visible and the tab raises no success toast.
- exception model: unexpected exceptions from the gate-answering call, the log append, or the broadcasts are not converted into an acknowledgement or failure frame by this command format, and earlier side effects are not rolled back.
- ignored data: keys other than `cmd`, `workflow_id`, `file_path`, and `answer` are ignored by the command handler.

## Fields

### field-cmd

- type: string JSON value emitted by the first-party form; any JSON value is accepted by the handler for comparison.
- default: absent
- required: true for the first-party answer command; required for handling, because any value other than exact string `"answer"` — including an absent value — is not handled by this format.
- wire-key: `cmd`
- producer-control: hidden input `name="cmd" value="answer"`.
- consumer-use: command discriminator checked before any workflow lookup, gate-answering call, log entry, or push.
- meaning: the command discriminator. It travels as a form control rather than being added by the sender, so one delegated listener can serve every command form the dashboard grows without knowing what any of them mean.

### field-workflow_id

- type: string-convertible JSON value
- default: `""`
- required: true for a successful gate answer; missing or blank values are still normalized and delegated to the gate-answering layer, which returns the failure result.
- wire-key: `workflow_id`
- producer-control: hidden input `name="workflow_id"`, rendered from the open run's container id.
- consumer-use: converted with `str(value)`, used as the workflow registry key, passed to the gate-answering call as the container id, copied into the answer log entry, and echoed as `id` in the success-only answered message.
- meaning: the workflow container id the answer is addressed to. It is rendered into the form from the detail payload the tab already holds, so the value is the run the operator is looking at rather than whatever the selection happens to be when submit fires.

### field-file_path

- type: string-convertible JSON value
- default: `""`
- required: true for a successful gate answer; missing or blank values are still normalized and delegated to the gate-answering layer, which returns the failure result.
- wire-key: `file_path`
- producer-control: hidden input `name="file_path"`, rendered from the open gate's context-file path.
- consumer-use: converted with `str(value)`, passed as the target gate path, copied into the answer log entry, and echoed in the success-only answered message.
- meaning: the gate context-file path this answer writes to. One form is rendered per open gate, so the value scopes the write to the gate whose button was pressed even when the run has several waiting.

### field-answer

- type: string-convertible JSON value
- default: `""`
- required: false
- wire-key: `answer`
- producer-control: textarea `name="answer"` with an explicit accessible name, rendered in each open gate's answer form.
- consumer-use: converted with `str(value)` and passed only to the gate-answering layer. It is not copied into the answer log entry, the state payload, or the answered message.
- meaning: the operator-authored answer text. Blank answers are blocked by neither the browser nor the command handler; the gate-answering layer receives the normalized string and decides the resulting gate-file update.
- retention: the textarea is cleared only when the send guard reports the frame was written. A refused send keeps the text, because the operator's typing is the one thing on this path that cannot be reconstructed from server state.
