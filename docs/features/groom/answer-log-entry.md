---
type: format
slug: answer-log-entry
title: Answer log entry
---
# Answer log entry

Answer log entry is the process-local event record appended to the [answer event log](concepts/answer-event-log.md) after the dashboard websocket handler attempts to answer a gate. It joins the submitted [dashboard websocket answer frame](dashboard-websocket-answer-frame.md) with the resulting [answer result](answer-result.md), so the `groom` process log can retain the container id, gate file path, success flag, and outcome message for the attempt handled through [WS /ws](http/groom.md#websocket-dashboard). The dashboard command handler constructs the dictionary and [record answer log entry](concepts/answer-event-log.md#method-record-answer-log-entry) appends that exact object to the bounded in-memory log.

- file: not an on-disk artifact; this is one dictionary stored in the in-memory [answer event log](concepts/answer-event-log.md).
- code: groom/groom/app.py::_handle_command

## Contract

- producer: the dashboard websocket command handler builds exactly one entry after each `cmd="answer"` frame reaches the gate-answering layer and receives an [answer result](answer-result.md), then appends that same dictionary through [record answer log entry](concepts/answer-event-log.md#method-record-answer-log-entry).
- skipped commands: frames whose `cmd` is absent or not exactly `"answer"` do not produce log entries.
- construction point: the entry is created only after `answer_gate(container_id, file_path, answer, workspace_volume=workspace_volume)` returns; exceptions raised before that point are not represented by an answer log entry.
- object shape: each entry is a plain dictionary with exactly the first-party keys `event`, `container_id`, `file_path`, `ok`, and `message` when produced by the dashboard websocket answer handler; there are no optional first-party keys.
- key names: field names are the exact dictionary keys used inside the process-local entry; this format has no wire aliases, version key, request id, timestamp, or correlation id.
- storage: entries are appended to the process-local [answer event log](concepts/answer-event-log.md); the same dictionary object is passed to the log without validation, cloning, redaction, timestamping, disk persistence, external sink, acknowledgement frame, or retry path.
- ordering: append order is the order in which answer attempts complete inside the single groom process, after gate-answering returns and before any successful-answer workflow-state flip or dashboard broadcast for that attempt.
- retention: the log deque keeps its configured bounded history; older entries may be discarded when the process exceeds that bound.
- relation: `ok` and `message` are copied from the [answer result](answer-result.md), while `container_id` and `file_path` are copied from the normalized submitted [dashboard websocket answer frame](dashboard-websocket-answer-frame.md) values.
- normalization: `container_id`, `file_path`, and the submitted answer text are independently converted with `str(value)` from the inbound websocket frame defaults, but only `container_id` and `file_path` are retained in this entry.
- excluded data: the submitted answer text, gate question, workspace volume, workflow state, browser event detail, rendered HTML fragment, timestamp, operator identity, and websocket client identifier are not stored in this entry.
- failure model: failed answer attempts are still logged with `ok: false` and the failure message returned by the gate-answering layer; append failures are not converted into response frames by this format.

## Fields

### field-event

- type: `str`
- default: none
- required: true
- key: `event`
- source: fixed literal set by the dashboard websocket command handler.
- domain: exactly `"answer"` for all first-party entries of this format.
- meaning: event discriminator identifying this dictionary as an answer attempt record; no other event value is produced for this format by the dashboard websocket answer handler.
- consumer-use: retained as part of the logged dictionary; no current first-party reader branches on it.

### field-container-id

- type: `str`
- default: `""`
- required: true
- key: `container_id`
- source: submitted `workflow_id` value from the handled [dashboard websocket answer frame](dashboard-websocket-answer-frame.md) after `str(value)` normalization.
- domain: any string produced by normalization; missing values become the empty string and the handler does not truncate the id for this log entry.
- meaning: container/workflow identifier used for the answer attempt and retained for process-local diagnostics.
- consumer-use: retained as part of the logged dictionary; the dashboard broadcast and answered browser event use the same local variable but do not read it back from the log entry.

### field-file-path

- type: `str`
- default: `""`
- required: true
- key: `file_path`
- source: submitted gate context-file path from the handled [dashboard websocket answer frame](dashboard-websocket-answer-frame.md) after `str(value)` normalization.
- domain: any string produced by normalization; missing values become the empty string and this format does not enforce path safety or existence.
- meaning: gate file path used for the answer attempt and retained for process-local diagnostics.
- consumer-use: retained as part of the logged dictionary; the dashboard broadcast and answered browser event use the same local variable but do not read it back from the log entry.

### field-ok

- type: `bool`
- default: none
- required: true
- key: `ok`
- source: copied from `AnswerResult.ok` in the gate-answering [answer result](answer-result.md).
- domain: first-party values are `true` or `false`.
- meaning: success flag for the answer attempt; `true` means the dashboard treats the answer attempt as successful and `false` means the attempt failed but was still recorded.
- consumer-use: retained as part of the logged dictionary; the successful-answer workflow-state flip and answered browser event are driven by the same `AnswerResult.ok` value before and after logging, not by reading this field back from the log.

### field-message

- type: `str`
- default: `""`
- required: true
- key: `message`
- source: copied from `AnswerResult.message` in the gate-answering [answer result](answer-result.md).
- domain: first-party values are the success and failure messages defined by [answer result](answer-result.md); the log entry also accepts the empty string or any arbitrary string already present on the result.
- meaning: operator-facing outcome text explaining the success path or failure reason.
- consumer-use: retained as part of the logged dictionary; no current first-party reader parses it, broadcasts it, or maps it to UI state.
