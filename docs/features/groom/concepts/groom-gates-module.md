---
type: concept
slug: groom-gates-module
title: Groom gates module
---
# Groom gates module

Groom gates module is the code boundary that owns Groom's shared operator-gate status tokens, [operator gate context file](../operator-gate-context-file.md) text parsing and answer text mutation helpers, and the asynchronous [gate-answering layer](gate-answering-layer.md). It is consumed by host-side discovery, the sidecar snapshot path, and dashboard answer handling so all gate readers and writers agree on the same `STATUS:` lifecycle semantics. Its answer operation composes the [per-gate answer lock](per-gate-answer-lock.md), [workspace volume file-content reader](workspace-volume-file-content-reader.md), [workspace volume file writer](workspace-volume-file-writer.md), [workflow gate clearer](workflow-gate-clearer.md), [container running-state check](container-running-state-check.md), and [stopped container start fallback](stopped-container-start-fallback.md) and reports its terminal domain outcome as an [answer result](../answer-result.md).

- code: groom/groom/gates.py
- verify: groom/tests/test_gates.py::test_status_of_reads_the_status_line
- verify: groom/tests/test_gates.py::test_is_awaiting
- verify: groom/tests/test_gates.py::test_extract_question_pulls_the_named_section
- verify: groom/tests/test_gates.py::test_extract_question_falls_back_to_whole_text_when_no_header
- verify: groom/tests/test_gates.py::test_apply_answer_flips_status_and_appends_text
- verify: groom/tests/test_gates.py::test_apply_answer_with_blank_answer_still_flips_status
- verify: groom/tests/test_gates.py::test_answer_gate_rejects_when_already_answered
- verify: groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running
- verify: groom/tests/test_gates.py::test_answer_gate_restarts_when_container_stopped
- verify: groom/tests/test_gates.py::test_answer_gate_reports_missing_workspace_volume
- refs: [operator gate context file](../operator-gate-context-file.md), [gate-answering layer](gate-answering-layer.md), [per-gate answer lock](per-gate-answer-lock.md), [workspace volume file-content reader](workspace-volume-file-content-reader.md), [workspace volume file writer](workspace-volume-file-writer.md), [workflow gate clearer](workflow-gate-clearer.md), [container running-state check](container-running-state-check.md), [stopped container start fallback](stopped-container-start-fallback.md), [answer result](../answer-result.md)

## Contract

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
- failure model: pure string helpers intentionally return fallback values rather than domain failures; [answer-gate](#answer-gate) returns `AnswerResult(ok=False, message=...)` for expected domain rejections and propagates unexpected Docker helper, path-safety, subprocess, and lock/runtime exceptions.
- external boundary: the standard-library regular expression runtime and asyncio thread offloading are below this module; the Docker and state helpers it calls are Groom concepts documented separately and are not re-specified here.
- non-effect: does not render dashboard fragments, broadcast websocket messages, validate websocket command frames, discover workflow containers, or persist any database record.

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
- code: groom/groom/gates.py::status_of
- verify: groom/tests/test_gates.py::test_status_of_reads_the_status_line
- detail: [operator gate context file status parser](../operator-gate-context-file.md#method-status-of)

Parses one supplied gate-file text string into the normalized lifecycle token used by discovery and stale-answer checks.

#### Effects

- reads: only the supplied text string.
- matches: the first line-start `STATUS:` token accepted by the [operator gate context file](../operator-gate-context-file.md#field-status-line) contract.
- normalizes: uppercases the captured token before returning it.
- fallback: returns the empty string when no status line with a token exists.
- calls: no other Groom source symbol.
- does not mutate: gate file text, workspace volumes, Docker containers, in-memory workflow state, gate locks, answer logs, dashboard clients, or rendered fragments.

### is-awaiting

- sig: `is_awaiting(text: str) -> bool`
- abstract: false
- raises: none intentionally raised for any string input.
- returns: `true` only when [status-of](#status-of) returns [field-awaiting](#field-awaiting).
- code: groom/groom/gates.py::is_awaiting
- verify: groom/tests/test_gates.py::test_is_awaiting
- detail: [operator gate context file awaiting classifier](../operator-gate-context-file.md#method-is-awaiting)

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
- code: groom/groom/gates.py::extract_question
- verify: groom/tests/test_gates.py::test_extract_question_pulls_the_named_section
- verify: groom/tests/test_gates.py::test_extract_question_falls_back_to_whole_text_when_no_header
- detail: [operator gate context file question extractor](../operator-gate-context-file.md#method-extract-question)

Extracts the operator-facing question preview from one gate file for gate records and dashboard displays.

#### Effects

- reads: only the supplied text string.
- matches: the first recognized singular or plural question heading described by [field-question-section](../operator-gate-context-file.md#field-question-section).
- selects: the stripped recognized section body when present, otherwise the stripped whole text string.
- limits: returns at most the first 4000 characters of the selected text.
- calls: no other Groom source symbol.
- does not mutate: gate file text, workspace volumes, Docker containers, in-memory workflow state, gate locks, answer logs, dashboard clients, or rendered fragments.

### apply-answer

- sig: `apply_answer(text: str, answer: str) -> str`
- abstract: false
- raises: none intentionally raised for any string input; invalid or missing status content is preserved except that no status can be flipped when no status line matches.
- returns: file text with the first matched status line changed to [field-answered](#field-answered) and the stripped non-blank answer appended as the final paragraph.
- code: groom/groom/gates.py::apply_answer
- verify: groom/tests/test_gates.py::test_apply_answer_flips_status_and_appends_text
- verify: groom/tests/test_gates.py::test_apply_answer_with_blank_answer_still_flips_status
- detail: [operator gate context file answer applier](../operator-gate-context-file.md#method-apply-answer)

Builds the answered form of one gate file text string without performing the file write or stale-state check.

#### Effects

- reads: the supplied gate file text and submitted answer string only.
- status mutation: replaces at most the first matched status line with `STATUS: ANSWERED`.
- answer normalization: strips surrounding whitespace from the submitted answer before deciding whether to append it.
- answer append: appends a non-blank stripped answer as the final paragraph after one blank line and a trailing newline.
- blank-answer rule: with a blank stripped answer, returns the status-updated text without adding an answer paragraph or trimming trailing content.
- calls: no other Groom source symbol.
- does not mutate: workspace volumes, Docker containers, in-memory workflow state, gate locks, answer logs, dashboard clients, or rendered fragments.

### answer-gate

- sig: `async answer_gate(container_id: str, file_path: str, answer: str, *, workspace_volume: str) -> AnswerResult`
- abstract: false
- raises: propagates exceptions from Docker volume access, container-status helpers, and unsafe path validation; expected domain failures are represented as `AnswerResult(ok=False, message=...)`.
- returns: an [answer result](../answer-result.md) indicating whether the answer file write was rejected, applied, applied with no restart needed, or applied with a stopped-container restart fallback.
- code: groom/groom/gates.py::answer_gate
- verify: groom/tests/test_gates.py::test_answer_gate_rejects_when_already_answered
- verify: groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running
- verify: groom/tests/test_gates.py::test_answer_gate_restarts_when_container_stopped
- verify: groom/tests/test_gates.py::test_answer_gate_reports_missing_workspace_volume
- detail: [gate-answering layer operation](gate-answering-layer.md#answer-gate)

Applies one submitted operator answer to one awaiting gate file in a workspace volume and returns the domain outcome used by the dashboard websocket handler.

#### Effects

- validates: rejects an empty `workspace_volume` before acquiring a lock or attempting any Docker, file, state, or restart side effect.
- locks: obtains and acquires the [per-gate answer lock](per-gate-answer-lock.md#method-gate-lock) scoped to the exact `container_id` and `file_path` pair.
- reads: rereads the current gate file text through the [workspace volume file-content reader](workspace-volume-file-content-reader.md) while the per-gate lock is held.
- stale guard: rejects missing files and any current text for which [is-awaiting](#is-awaiting) is false before writing.
- builds: calls [apply-answer](#apply-answer) to create the updated file text.
- writes: streams the updated text to the same workspace volume and path through the [workspace volume file writer](workspace-volume-file-writer.md).
- clears state: after a successful write, calls the [workflow gate clearer](workflow-gate-clearer.md#method-clear-gate) for the same `container_id` and `file_path`.
- running path: if the [container running-state check](container-running-state-check.md) reports the container is still running, returns success without starting it.
- stopped fallback: if the running-state check reports stopped, attempts the [stopped container start fallback](stopped-container-start-fallback.md) and reports whether the restart succeeded.
- calls: `state.gate_lock`, `docker_io.read_file`, [is-awaiting](#is-awaiting), [apply-answer](#apply-answer), `docker_io.write_file`, `state.clear_gate`, `docker_io.is_running`, and `docker_io.docker_start`.

## Algorithms

### algorithm-module-initialization

- step: Bind the public status token constants [field-awaiting](#field-awaiting), [field-answered](#field-answered), and [field-consumed](#field-consumed).
- step: Bind private parser state for the [operator gate context file](../operator-gate-context-file.md): one status-line pattern, one question-section pattern, and the 4000-character question preview limit.
- step: Expose four pure text helpers and one asynchronous gate-answering operation.
- step: Complete import without inspecting Docker, opening a workspace volume, reading a gate file, writing a gate file, mutating state, acquiring a gate lock, or emitting dashboard output.

### algorithm-answer-gate-outcomes

- step: Return `AnswerResult(ok=False, message="unknown workspace volume for this container")` when no workspace volume is supplied.
- step: Return `AnswerResult(ok=False, message="gate file not found")` when the locked workspace-volume read cannot load the selected file.
- step: Return `AnswerResult(ok=False, message="already answered in another tab")` when the locked reread no longer has the awaiting token.
- step: Return `AnswerResult(ok=False, message="failed to write answer")` when the updated text is built but the workspace-volume writer reports failure.
- step: Return `AnswerResult(ok=True, message="answered")` when the write succeeds and the workflow container is still running.
- step: Return `AnswerResult(ok=True, message="answered and restarted")` when the write succeeds, the container is stopped, and the stopped-container start fallback succeeds.
- step: Return `AnswerResult(ok=True, message="answer written but restart failed — start the container manually")` when the write succeeds but the stopped-container start fallback reports failure.
