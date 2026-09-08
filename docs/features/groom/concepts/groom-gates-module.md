---
type: concept
slug: groom-gates-module
title: Groom gates module
---
# Groom gates module

Groom gates module is the code boundary that owns Groom's shared operator-gate status tokens, [operator gate context file](../operator-gate-context-file.md) text parsing and answer text mutation helpers, and the asynchronous [gate-answering layer](gate-answering-layer.md). It is consumed by host-side discovery, the sidecar snapshot path, and dashboard answer handling so all gate readers and writers agree on the same `STATUS:` lifecycle semantics. Its answer operation composes the [per-gate answer lock](per-gate-answer-lock.md), [workspace volume file-content reader](workspace-volume-file-content-reader.md), [workspace volume file writer](workspace-volume-file-writer.md), [workflow gate clearer](workflow-gate-clearer.md), [container running-state check](container-running-state-check.md), and [stopped container start fallback](stopped-container-start-fallback.md) and reports its terminal domain outcome as an [answer result](../answer-result.md).

- code: groom/groom/gates.py
- tests: groom/tests/test_gates.py::test_apply_answer_flips_status_and_appends_text
- tests: groom/tests/test_gates.py::test_apply_answer_with_blank_answer_still_flips_status
- refs: [operator gate context file](../operator-gate-context-file.md), [gate-answering layer](gate-answering-layer.md), [per-gate answer lock](per-gate-answer-lock.md), [workspace volume file-content reader](workspace-volume-file-content-reader.md), [workspace volume file writer](workspace-volume-file-writer.md), [workflow gate clearer](workflow-gate-clearer.md), [container running-state check](container-running-state-check.md), [stopped container start fallback](stopped-container-start-fallback.md), [answer result](../answer-result.md)

The module-level test coverage includes `test_status_of_reads_the_status_line`,
`test_is_awaiting`, `test_extract_question_pulls_the_named_section`,
`test_extract_question_falls_back_to_whole_text_when_no_header`,
`test_answer_gate_rejects_when_already_answered`,
`test_answer_gate_writes_answer_no_restart_when_still_running`,
`test_answer_gate_restarts_when_container_stopped`, and
`test_answer_gate_reports_missing_workspace_volume`. The answer-text tests also check that one
`STATUS: ANSWERED` line and one submitted non-blank answer occur in the returned gate text.

## Contract

In `groom/groom/gates.py::answer_gate`, anticipated domain rejections are represented by an
`AnswerResult` with `ok=False`; collaborator exceptions are not translated by this module. The
pure text helpers use the fallback outputs specified by their individual method contracts.

- purpose: provide one first-party source of truth for detecting open operator gates, extracting their human-facing prompt, transforming an accepted answer into file text, and orchestrating the host-side answer write.
- import behavior: importing the module binds the status constants, compiles the status and question parsers, and exposes the public helper functions; import does not read Docker, inspect containers, read or write gate files, acquire gate locks, mutate process state, render HTML, or broadcast websocket fragments.
- public data members: the public status-token fields are exactly `AWAITING`, `ANSWERED`, and `CONSUMED`.
- public function members: the public helpers are exactly `status_of`, `is_awaiting`, `extract_question`, `apply_answer`, and `answer_gate`.
- private parser members: `_STATUS_RE`, `_QUESTIONS_RE`, and `_QUESTION_PREVIEW_LIMIT` are private module implementation details folded into the [operator gate context file](../operator-gate-context-file.md) format contract rather than separate public concepts.
- file contract: every parser and writer in this module operates on the [operator gate context file](../operator-gate-context-file.md) text format rather than on rendered dashboard HTML, database rows, or Docker inspect metadata.
- status contract: the only public open-gate token is [field-awaiting](#field-awaiting), the only token this module writes is [field-answered](#field-answered), and [field-consumed](#field-consumed) is recognized as a non-awaiting lifecycle value for compatibility with wait scripts.
- purity boundary: [status-of](#status-of), [is-awaiting](#is-awaiting), [extract-question](#extract-question), and [apply-answer](#apply-answer) are deterministic string helpers with no Docker, state, network, filesystem, or dashboard side effects.
- orchestration boundary: [answer-gate](#answer-gate) delegates the host-side answer operation to the grounded [gate-answering layer](gate-answering-layer.md), which is the only public member that reads or writes a workspace volume, acquires a per-gate lock, clears process-local gate state, or starts a stopped container.
- concurrency boundary: answering is scoped to one `(container_id, file_path)` pair; this module does not assume a workflow container has only one live gate.
- external boundary: the standard-library regular expression runtime and asyncio thread offloading are below this module; the Docker and state helpers it calls are Groom concepts documented separately and are not re-specified here.
- non-effect: does not project dashboard payloads, broadcast websocket messages, validate websocket command frames, discover workflow containers, or persist any database record.

## Fields

### field-awaiting

- type: status token string
- default: `"AWAITING_OPERATOR"`
- required: true
- code: groom/groom/gates.py::AWAITING
- meaning: marks an operator gate context file as open and answerable by Groom.
- used-by: [is-awaiting](#is-awaiting) and [answer-gate](#answer-gate) accept only this normalized token as the current file state for a submitted answer.

### field-answered

- type: status token string
- default: `"ANSWERED"`
- required: true
- code: groom/groom/gates.py::ANSWERED
- meaning: marks an operator gate context file as answered after a submitted operator response has been accepted.
- used-by: [apply-answer](#apply-answer) writes exactly this token into the first matched status line.

### field-consumed

- type: status token string
- default: `"CONSUMED"`
- required: true
- code: groom/groom/gates.py::CONSUMED
- meaning: names the wait-script consumed lifecycle state that Groom treats as non-awaiting.
- used-by: [status-of](#status-of) can return this normalized token, and [is-awaiting](#is-awaiting) rejects it.

## Methods

### status-of

- sig: `status_of(text: str) -> str`
- abstract: false
- raises: none intentionally raised for any string input.
- returns: the uppercased first status token, or `""` when the text has no matching status line.
- verify: json_path(path="return value", equals="AWAITING_OPERATOR")
- code: groom/groom/gates.py::status_of
- detail: [gate status parser documentation contexts](gate-status-parser-documentation-contexts.md)
- detail: [operator gate context file status parser](../operator-gate-context-file.md#method-status-of)
- tests: groom/tests/test_gates.py::test_status_of_reads_the_status_line

Parses one supplied gate-file text string into the normalized lifecycle token used by discovery and stale-answer checks. In `groom/groom/gates.py::status_of`, a text string without a matching status line returns an empty string.

#### Effects

- reads: only the supplied text string.
- matches: the first line-start `STATUS:` token accepted by the [operator gate context file](../operator-gate-context-file.md#field-status-line) contract.
- normalizes: uppercases the captured token before returning it.
- calls: no other Groom source symbol.
- does not mutate: gate file text, workspace volumes, Docker containers, in-memory workflow state, gate locks, answer logs, dashboard clients, or rendered fragments.

### is-awaiting

- sig: `is_awaiting(text: str) -> bool`
- abstract: false
- raises: none intentionally raised for any string input.
- returns: `true` only when [status-of](#status-of) returns [field-awaiting](#field-awaiting).
- verify: json_path(path="return value", equals=true)
- code: groom/groom/gates.py::is_awaiting
- detail: [operator gate context file awaiting classifier](../operator-gate-context-file.md#method-is-awaiting)
- detail: [is awaiting documentation contexts](is-awaiting-documentation-contexts.md)
- tests: groom/tests/test_gates.py::test_is_awaiting

Classifies whether one supplied gate-file text string is currently answerable by Groom.

#### Effects

- reads: only the supplied text string.
- calls: [status-of](#status-of) to obtain the normalized status token.
- compares: accepts only [field-awaiting](#field-awaiting) as the answerable lifecycle state.
- rejects: [field-answered](#field-answered), [field-consumed](#field-consumed), unknown tokens, missing status lines, and empty strings as non-awaiting.
- does not mutate: gate file text, workspace volumes, Docker containers, in-memory workflow state, gate locks, answer logs, dashboard clients, or rendered fragments.

### extract-question

- sig: `extract_question(text: str) -> str`
- abstract: false
- raises: none intentionally raised for any string input.
- returns: the recognized agent question section body, or the stripped whole text fallback, truncated to the operator preview limit.
- verify: count(subject="recognized question text in returned preview", equals=1)
- verify: count(subject="unrelated context section text in returned question preview", equals=0)
- verify: count(subject="stripped whole gate text in returned question preview", equals=1)
- code: groom/groom/gates.py::extract_question
- detail: [gate question extraction contexts](gate-question-extraction-contexts.md)
- tests: groom/tests/test_gates.py::test_extract_question_pulls_the_named_section
- tests: groom/tests/test_gates.py::test_extract_question_falls_back_to_whole_text_when_no_header

Extracts the operator-facing question preview from one gate file for gate records and dashboard displays. In `groom/groom/gates.py::extract_question`, the selected text is truncated to its first 4000 characters.

#### Effects

- reads: only the supplied text string.
- matches: every recognized singular or plural question heading described by [field-question-section](../operator-gate-context-file.md#field-question-section).
- selects: the stripped body of the latest recognized section when present, otherwise the stripped whole text string.
- calls: no other Groom source symbol.
- does not mutate: gate file text, workspace volumes, Docker containers, in-memory workflow state, gate locks, answer logs, dashboard clients, or rendered fragments.

### apply-answer

- sig: `apply_answer(text: str, answer: str) -> str`
- abstract: false
- raises: none intentionally raised for any string input.
- raises: invalid or missing status content is preserved except that no status can be flipped when no status line matches.
- returns: file text with the first matched status line changed to [field-answered](#field-answered) and the stripped non-blank answer appended as the final paragraph.
- verify: count(subject="STATUS: ANSWERED lines in returned gate text", equals=1)
- verify: count(subject="submitted non-blank answer occurrences in returned gate text", equals=1)
- code: groom/groom/gates.py::apply_answer
- detail: [operator gate context file answer applier](../operator-gate-context-file.md#method-apply-answer)
- detail: [gate answer text mutation](gate-answer-text-mutation.md)
- tests: groom/tests/test_gates.py::test_apply_answer_flips_status_and_appends_text
- tests: groom/tests/test_gates.py::test_apply_answer_with_blank_answer_still_flips_status

Builds the answered form of one gate file text string without performing the file write or stale-state check. In `groom/groom/gates.py::apply_answer`, a blank stripped answer leaves the status-updated text otherwise unchanged, including its trailing content.

#### Effects

- reads: the supplied gate file text and submitted answer string only.
- status mutation: replaces at most the first matched status line with `STATUS: ANSWERED`.
- answer normalization: strips surrounding whitespace from the submitted answer before deciding whether to append it.
- answer append: appends a non-blank stripped answer as the final paragraph after one blank line and a trailing newline.
- calls: no other Groom source symbol.
- does not mutate: workspace volumes, Docker containers, in-memory workflow state, gate locks, answer logs, dashboard clients, or rendered fragments.

### answer-gate

- sig: `async answer_gate(container_id: str, file_path: str, answer: str, *, workspace_volume: str) -> AnswerResult`
- abstract: false
- raises: propagates exceptions from Docker volume access, container-status helpers, and unsafe path validation.
- raises: represents expected domain failures as `AnswerResult(ok=False, message=...)`.
- returns: an [answer result](../answer-result.md) indicating whether the answer file write was rejected, applied, applied with no restart needed, or applied with a stopped-container restart fallback.
- verify: conflict_on_stale(subject="gate file")
- code: groom/groom/gates.py::answer_gate
- detail: [gate-answering layer operation](gate-answering-layer.md#answer-gate)
- tests: groom/tests/test_gates.py::test_answer_gate_rejects_when_already_answered
- tests: groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running
- tests: groom/tests/test_gates.py::test_answer_gate_restarts_when_container_stopped
- tests: groom/tests/test_gates.py::test_answer_gate_reports_missing_workspace_volume

Applies one submitted operator answer to one awaiting gate file in a workspace volume and returns the domain outcome used by the dashboard websocket handler. In `groom/groom/gates.py::answer_gate`, an empty workspace-volume value returns the unknown-volume domain result before the function obtains a lock or performs Docker, file, state, or restart work. Once the lock is held, the reread text is what a second browser tab racing to answer the same gate would see — a missing file or a reread that no longer satisfies [is-awaiting](#is-awaiting) is the stale case, and the guarded outcomes it produces before any write is attempted are the `"gate file not found"` and `"already answered in another tab"` results recorded in [algorithm-answer-gate-outcomes](#algorithm-answer-gate-outcomes). After the write, the function consults the [container running-state check](container-running-state-check.md): a container it finds still running short-circuits the restart path, while a stopped container routes into the [stopped container start fallback](stopped-container-start-fallback.md) — the resulting `"answered"`, `"answered and restarted"`, and restart-failed outcomes are the same three recorded in [algorithm-answer-gate-outcomes](#algorithm-answer-gate-outcomes).

#### Effects

- locks: obtains and acquires the [per-gate answer lock](per-gate-answer-lock.md#method-gate-lock) scoped to the exact `container_id` and `file_path` pair.
- reads: rereads the current gate file text through the [workspace volume file-content reader](workspace-volume-file-content-reader.md) while the per-gate lock is held.
- builds: calls [apply-answer](#apply-answer) to create the updated file text.
- writes: streams the updated text to the same workspace volume and path through the [workspace volume file writer](workspace-volume-file-writer.md).
- clears state: after a successful write, calls the [workflow gate clearer](workflow-gate-clearer.md#method-clear-gate) for the same `container_id` and `file_path`.
- stopped fallback: if the running-state check reports stopped, attempts the [stopped container start fallback](stopped-container-start-fallback.md) and reports whether the restart succeeded.
- calls: `state.gate_lock`, `docker_io.read_file`, [is-awaiting](#is-awaiting), [apply-answer](#apply-answer), `docker_io.write_file`, `state.clear_gate`, `docker_io.is_running`, and `docker_io.docker_start`.

## Algorithms

### algorithm-module-initialization

- step: Bind the public status token constants [field-awaiting](#field-awaiting), [field-answered](#field-answered), and [field-consumed](#field-consumed).
- step: Bind private parser state for the [operator gate context file](../operator-gate-context-file.md): one status-line pattern, one question-section pattern, and the 4000-character question preview limit.
- step: Expose four pure text helpers and one asynchronous gate-answering operation.
- step: Complete import without inspecting Docker, opening a workspace volume, reading a gate file, writing a gate file, mutating state, acquiring a gate lock, or emitting dashboard output.

### algorithm-answer-gate-outcomes

`groom/groom/gates.py::answer_gate` returns the following domain outcomes for its guarded write and restart paths.

- consistency: answer-result — returns `AnswerResult(ok=False, message="unknown workspace volume for this container")` when no workspace volume is supplied.
- consistency: answer-result — returns `AnswerResult(ok=False, message="gate file not found")` when the locked workspace-volume read cannot load the selected file.
- consistency: answer-result — returns `AnswerResult(ok=False, message="already answered in another tab")` when the locked reread no longer has the awaiting token.
- consistency: answer-result — returns `AnswerResult(ok=False, message="failed to write answer")` when the updated text is built but the workspace-volume writer reports failure.
- consistency: answer-result — returns `AnswerResult(ok=True, message="answered")` when the write succeeds and the workflow container is still running.
- consistency: answer-result — returns `AnswerResult(ok=True, message="answered and restarted")` when the write succeeds and the stopped container restarts successfully.
- consistency: answer-result — returns `AnswerResult(ok=True, message="answer written but restart failed — start the container manually")` when the write succeeds but the stopped-container start fallback reports failure.
