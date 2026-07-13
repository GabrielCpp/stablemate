---
type: format
slug: answer-result
title: Answer result
---
# Answer result

Answer result is the in-memory return object from the [gate-answering layer](concepts/gate-answering-layer.md) consumed by the dashboard websocket answer handler. It reports whether a submitted [dashboard websocket answer frame](dashboard-websocket-answer-frame.md) changed the target [gate info](concepts/gate-info.md), supplies the operator-facing outcome text copied into an [answer log entry](answer-log-entry.md), and determines whether the [groom dashboard](gui/screens/groom-dashboard.md) receives a `groom:answered` success event after [WS /ws](http/groom.md#websocket-dashboard) handles the submission. The shape is the `AnswerResult` dataclass; the gate-answering call is the first-party producer of the currently defined success and failure messages, and the websocket command handler is the first-party consumer that turns the result into logging, state, and broadcast effects.

- file: not an on-disk artifact; this is a process-local dataclass value returned by the gate-answering call.
- code: groom/groom/models.py::AnswerResult
- verify: groom/tests/test_gates.py::test_answer_gate_rejects_when_already_answered
- verify: groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running
- verify: groom/tests/test_gates.py::test_answer_gate_restarts_when_container_stopped
- verify: groom/tests/test_gates.py::test_answer_gate_reports_missing_workspace_volume
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch

## Contract

- producer: the [gate-answering layer](concepts/gate-answering-layer.md) returns exactly one result for every attempted answer command that reaches it.
- consumer: the dashboard websocket command handler reads `ok` and `message` after the gate-answering call completes.
- medium: process-local Python object; it is not a JSON frame, HTML fragment, persisted log record, or file format.
- constructor: `AnswerResult(ok: bool, message: str = "")`.
- construction: callers must supply `ok`; callers may omit `message`, in which case the object exposes `message=""`.
- field order: `ok` is the first constructor and storage field; `message` is second.
- attributes: exactly `ok` and `message` are part of this return shape; container id, gate file path, submitted answer text, question text, workspace volume, restart status, and exception data are not fields.
- mutability: instances are mutable process-local records; neither field is frozen or computed.
- validation: the shape itself does not validate or coerce field values; first-party producers pass a boolean `ok` and a string `message`.
- success meaning: `ok=true` means the gate file write succeeded and the dashboard treats the selected gate as answered, even if the fallback container restart failed after the write.
- failure meaning: `ok=false` means the answer was not applied because the workspace volume was unknown, the gate file could not be read, the gate was no longer awaiting an answer, or the rewritten gate file could not be written.
- success messages: first-party successful results use `"answered"` when the container was still running, `"answered and restarted"` when a stopped container was restarted after the write, or `"answer written but restart failed — start the container manually"` when the write succeeded but the fallback restart did not.
- failure messages: first-party failed results use `"unknown workspace volume for this container"`, `"gate file not found"`, `"already answered in another tab"`, or `"failed to write answer"`.
- exception boundary: unsafe file paths, Docker helper exceptions, subprocess launch failures, and restart timeouts are not represented as answer-result values when they propagate out of the gate-answering layer.
- consumer mapping: `ok` is copied unchanged into the answer log and gates the success-only state and broadcast additions; `message` is copied unchanged into the answer log and is not included in the `groom:answered` browser event detail.
- broadcast effect: every result, successful or failed, causes a refreshed dashboard shell broadcast; only successful results append the `groom:answered` script.
- log effect: every result is copied into one [answer log entry](answer-log-entry.md) with the submitted container id and gate file path.
- state effect: successful results allow the websocket handler to mark a blocked workflow as running immediately when the answered gate was the last visible gate; failed results leave workflow state and visible gates unchanged except for the refreshed shell broadcast.

## Fields

### field-ok

- type: `bool`
- default: none
- required: true
- domain: first-party values are `true` or `false`.
- producer-use: set by the gate-answering layer after the answer attempt reaches a terminal domain outcome.
- consumer-use: copied into the [answer log entry](answer-log-entry.md), checked before appending the [groom answered script fragment](groom-answered-script-fragment.md), and checked before changing a blocked workflow with no remaining visible gates to running.
- meaning: success flag consumed by the websocket handler to decide whether to emit the `groom:answered` event and whether a blocked, gate-less workflow should be shown as running immediately. `true` requires that the target gate file was rewritten to the answered state; `false` means no answer write was accepted.

### field-message

- type: `str`
- default: `""`
- required: false for construction; the dataclass instance always exposes the attribute and uses the empty string when the caller omits it.
- domain: first-party non-empty values are the success and failure strings listed in the contract; the shape itself also permits the empty default and arbitrary caller-supplied strings.
- producer-use: set by the gate-answering layer to summarize the accepted write, duplicate/stale gate, missing file, missing workspace volume, write failure, or restart fallback outcome.
- consumer-use: copied verbatim into the [answer log entry](answer-log-entry.md); not used to decide success, not sent in the `groom:answered` event detail, and not parsed by the websocket handler.
- meaning: operator-facing outcome text recorded into the answer event log entry; first-party values are the success and failure messages listed in the contract, but the dataclass itself does not restrict the string.
