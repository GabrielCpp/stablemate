---
type: format
slug: operator-gate-context-file
title: Operator gate context file
---
# Operator gate context file

Operator gate context file is the workspace-volume text artifact that represents
one live operator gate. The [Groom gates
module](concepts/groom-gates-module.md) owns the shared parser and writer contract
for this file. The [gate-answering
layer](concepts/gate-answering-layer.md) rereads it, rejects stale submissions
through [method-is-awaiting](#method-is-awaiting), and rewrites it to accept an
answer through [method-apply-answer](#method-apply-answer), the [sidecar
snapshot](concepts/sidecar-snapshot.md) scans workspace files in this shape,
classifies each prefix through [method-status-of](#method-status-of), and
extracts the retained prompt through
[method-extract-question](#method-extract-question) to produce [sidecar snapshot
data](sidecar-snapshot-data.md), and each awaiting file becomes one in-memory
[gate info](concepts/gate-info.md) record keyed by the file's workspace-relative
path. Host-side discovery reaches the same file shape through the [workspace
volume awaiting file reader](concepts/workspace-volume-awaiting-file-reader.md),
then rereads and reclassifies each candidate before creating gate info.

- file: arbitrary workspace-relative path inside a workflow container's `/workspace` tree; common paths vary by workflow node and are not fixed by groom.
- code: groom/groom/gates.py::_STATUS_RE
- verify: groom/tests/test_gates.py::test_status_of_reads_the_status_line
- verify: groom/tests/test_gates.py::test_is_awaiting
- verify: groom/tests/test_gates.py::test_extract_question_pulls_the_named_section
- verify: groom/tests/test_gates.py::test_extract_question_falls_back_to_whole_text_when_no_header
- verify: groom/tests/test_gates.py::test_apply_answer_flips_status_and_appends_text
- verify: groom/tests/test_gates.py::test_apply_answer_with_blank_answer_still_flips_status
- verify: groom/tests/test_discovery.py::test_find_gates_only_keeps_files_still_awaiting
- verify: groom/tests/test_sidecar.py::test_scan_gates_finds_awaiting_and_skips_git_and_non_awaiting

## Contract

- media: line-oriented text, usually Markdown-like context, decoded by groom with replacement for invalid characters when scanning from the sidecar.
- identity: the file path is outside the file content; groom carries it as a workspace-relative string in gate records, snapshot entries, hidden answer inputs, and answer frames.
- status rule: the file is classified by the first line matching `STATUS:[ \t]*(\S+)` at the start of a line; the captured token is returned uppercased, and the absence of a matching token is represented as `""`.
- status token rule: the shared parser requires a non-whitespace token after the colon; `STATUS:` by itself, leading whitespace before `STATUS:`, and any line that only resembles a status line outside the line-start pattern are treated as no status by first-party parsers.
- awaiting rule: only the normalized status token `AWAITING_OPERATOR` is answerable and discoverable as an open gate.
- answered rule: accepting an answer replaces at most the first matched `STATUS:` line with `STATUS: ANSWERED`; when no status line matches, the file body is preserved and only a non-blank answer append can change the returned text.
- consumed rule: the normalized status token `CONSUMED` is recognized as a non-awaiting state; groom does not write it when answering.
- question rule: the operator-facing question is the stripped body of a `## Question from the agent` or `## Questions from the agent` section, matched case-insensitively with flexible whitespace and ending before the next heading marker that begins with at least two `#` characters or end of file.
- question heading rule: the recognized question marker is searched anywhere in the text and is not required to be the first heading; a same-line body after the heading marker is not a recognized section body because the parser requires at least one newline before captured question content.
- fallback question rule: when no recognized question section exists, the stripped whole file is used as the question text.
- preview limit: extracted question text is truncated to 4000 characters before it enters gate records or snapshot data.
- scan rule: the sidecar reads only the first 512 characters to decide whether a file is awaiting, then reads the full file only for retained awaiting files.
- scan path rule: first-party scans inspect regular files under the workspace volume while pruning `.git`, `node_modules`, `__pycache__`, and `.venv` directories; the sidecar uses a local workspace walk, while host discovery uses a read-only Docker volume sweep and then rereads retained candidates.
- host discovery rule: the host-side workspace-volume sweep first asks the volume reader for files with a line that starts with `STATUS:`, allows POSIX whitespace after the colon, and then contains `AWAITING_OPERATOR`; it then rereads each candidate through the shared parser and keeps it only if the current full content still normalizes to `AWAITING_OPERATOR`.
- answer append rule: answer text is stripped; a non-blank answer is appended after the existing file content as one trailing paragraph followed by a newline, while a blank answer only flips the status.
- preservation rule: context headings, prose, and any sections other than the first matched `STATUS:` line remain byte-order-equivalent in the rewritten output except for right-trimming before a non-blank appended answer.
- failure rule: a file with no status line is not awaiting, produces an empty status token, and is not answerable through the gate-answering layer.

## Fields

### field-status-line

- type: line matching `^STATUS:[ \t]*(\S+)` under multiline parsing
- default: absent
- required: true for an active operator gate
- meaning: declares the gate lifecycle token consumed by sidecar discovery and by the answer stale-state check.
- parse rule: may appear on any line that starts with `STATUS:` for the shared parser, though produced gate files put it first so the sidecar prefix scan can classify the file cheaply.
- token rule: the line must provide at least one non-whitespace token after optional spaces or tabs following the colon; additional text after the first token is ignored by the parser.
- discovery rule: first-party host discovery can discover candidates from any matching line in the file, while sidecar discovery needs the awaiting status to appear within the first 512 characters.
- write rule: the answer writer replaces only the first matched status line and leaves every later status-like line untouched.

### field-status-value

- type: enum string: `AWAITING_OPERATOR`, `ANSWERED`, `CONSUMED`, or another token treated as non-awaiting
- default: none
- required: true when `field-status-line` is present
- meaning: normalized lifecycle state for the gate file.
- parse rule: captured without following whitespace, uppercased before comparison, and returned as `""` when no status line exists.
- awaiting semantics: `AWAITING_OPERATOR` means the dashboard may show and submit an answer for this file.
- answered semantics: `ANSWERED` means an answer has been written and a competing answer must be rejected as stale.
- consumed semantics: `CONSUMED` means the in-container wait script has already consumed an answer or moved past the gate; groom treats it as non-awaiting.

### field-question-section

- type: Markdown section body
- default: stripped whole file text when the section is absent
- required: false
- code: groom/groom/gates.py::_QUESTIONS_RE
- meaning: human-facing question presented in the operator inbox, worker detail panel, and sidecar snapshot gate entries.
- heading rule: accepted heading text is `Question from the agent` or `Questions from the agent`, case-insensitive, preceded by at least two `#` characters in the matched text and followed by optional trailing whitespace before the body newline.
- match rule: the parser searches for the first matching marker anywhere in the text rather than requiring the marker to begin at the start of a line.
- boundary rule: extraction starts after one or more newlines following the heading and ends immediately before the next newline followed by a heading marker that begins with at least two `#` characters or at end of file.
- same-line rule: text on the same line as the recognized heading is not captured as a question section body; when no later recognized section body exists, extraction falls back to the stripped whole file.
- trim rule: leading and trailing whitespace around the extracted body is removed.
- limit: the retained question text is at most 4000 characters, as defined by `groom/groom/gates.py::_QUESTION_PREVIEW_LIMIT`.

### field-context-sections

- type: Markdown text and sections
- default: empty
- required: false
- meaning: any additional context the workflow wrote for the human operator or for the wait script.
- preservation rule: context sections are retained when an answer is applied; the question extractor ignores them unless the recognized question heading is absent, in which case the whole file becomes the fallback question text.

### field-answer-paragraph

- type: free text paragraph appended at the end of the file
- default: absent
- required: false
- meaning: operator-authored answer text that the in-container wait script observes after the status flips to `ANSWERED`.
- write rule: surrounding whitespace is stripped before appending.
- blank rule: a blank or all-whitespace submitted answer does not create this paragraph but still changes the status to `ANSWERED`.
- placement rule: a non-blank answer is appended after the right-trimmed existing file content, separated by one blank line, and terminated with a newline.

## Methods

### method-status-of

- sig: `status_of(text: str) -> str`
- abstract: false
- raises: none intentionally raised for any string input.
- code: groom/groom/gates.py::status_of
- verify: groom/tests/test_gates.py::test_status_of_reads_the_status_line

Parses one operator gate context file text into the normalized lifecycle token that consumers use for discovery, stale-answer checks, and non-awaiting filtering.

#### Effects

- Reads: the supplied text only.
- Input contract: accepts any string, including an empty string, partial file prefix, full file body, or non-Markdown text.
- Matches: the first substring that starts a line with `STATUS:`, allows only spaces or tabs after the colon, and captures the following non-whitespace token.
- Search scope: scans the whole supplied string under multiline line-start semantics; callers that pass only a prefix receive a prefix-only classification.
- Token boundary: captures exactly the first non-whitespace run after `STATUS:` and ignores any later words, punctuation, sections, or additional status-like lines.
- Normalizes: uppercases the captured token before returning it, so `consumed` and `CONSUMED` classify identically while preserving non-letter characters as part of the token.
- Unknown token rule: returns unknown status tokens after uppercasing rather than validating against the known lifecycle values; callers decide whether the token is answerable.
- Return contract: always returns a string and never `None`.
- Fallback: returns the empty string when no line has `STATUS:` followed by a token.
- Used by: [method-scan_gates](concepts/sidecar-snapshot.md#method-scan_gates) passes each file's initial 512-character prefix through this classifier and retains only the exact `AWAITING_OPERATOR` result.
- Calls: no other groom source symbols.
- Does not mutate: file text, workspace-volume files, gate records, workflow state, answer locks, dashboard clients, or sidecar sessions.

### method-is-awaiting

- sig: `is_awaiting(text: str) -> bool`
- abstract: false
- raises: none intentionally raised for any string input.
- code: groom/groom/gates.py::is_awaiting
- verify: groom/tests/test_gates.py::test_is_awaiting

Classifies whether one operator gate context file is currently answerable by comparing its normalized lifecycle token to the sole open-gate value.

#### Effects

- Reads: the supplied text only.
- Calls: [method-status-of](#method-status-of) to obtain the normalized status token.
- Parsing contract: performs no independent parsing; all status-line matching, multiline search scope, token capture, case normalization, unknown-token handling, and empty-string fallback are inherited from [method-status-of](#method-status-of).
- Compares against: [field-status-value](#field-status-value)'s `AWAITING_OPERATOR` token as the only answerable lifecycle state.
- Returns: `true` only when the normalized token is exactly `AWAITING_OPERATOR`.
- Rejects as false: `ANSWERED`, `CONSUMED`, an absent status line, an empty token, or any other token.
- Used by: [gate-answering layer](concepts/gate-answering-layer.md) after rereading the current file under the per-gate lock, so a browser tab can write only when the file is still awaiting at the time of submission.
- Does not mutate: file text, workspace-volume files, gate records, workflow state, answer locks, dashboard clients, or sidecar sessions.

### method-extract-question

- sig: `extract_question(text: str) -> str`
- abstract: false
- raises: none intentionally raised for any string input.
- code: groom/groom/gates.py::extract_question
- verify: groom/tests/test_gates.py::test_extract_question_pulls_the_named_section
- verify: groom/tests/test_gates.py::test_extract_question_falls_back_to_whole_text_when_no_header

Extracts the operator-facing prompt text from one gate file for [gate info](concepts/gate-info.md), sidecar snapshot gate entries, inbox previews, and worker-detail answer forms.

#### Effects

- Reads: the supplied text only.
- Matches: the first occurrence of a two-hash marker followed by `Question from the agent` or `Questions from the agent`, case-insensitively, with flexible whitespace before `Question`, between the words, and after `agent`.
- Marker scope: the marker does not have to begin at the start of a line; any earlier text is ignored once the marker is found, and if multiple recognized markers exist only the first one is used.
- Requires after heading: at least one newline after the recognized heading before
  the body starts; a same-line question after the heading is not a recognized
  section body and therefore falls back to whole-file extraction.
- Extracts: all text after the recognized heading's newline run and before the next newline followed by `##` or the end of the file.
- Fallback: uses the stripped whole file text when no recognized question heading exists.
- Normalizes: strips leading and trailing whitespace from the selected body before applying the preview limit.
- Limits: returns at most the first 4000 characters of the stripped selected body, counting Python string characters.
- Used by: [method-scan_gates](concepts/sidecar-snapshot.md#method-scan_gates)
  after a file is known to be awaiting, so the snapshot stores only the
  operator-facing prompt rather than the full gate context whenever the
  recognized question section is present.
- Calls: no other groom source symbols.
- Does not mutate: file text, workspace-volume files, gate records, workflow state, answer locks, dashboard clients, or sidecar sessions.

### method-apply-answer

- sig: `apply_answer(text: str, answer: str) -> str`
- abstract: false
- raises: none intentionally raised for any string input; invalid or missing gate status content is preserved except that no status line can be flipped when the status pattern is absent.
- code: groom/groom/gates.py::apply_answer
- verify: groom/tests/test_gates.py::test_apply_answer_flips_status_and_appends_text
- verify: groom/tests/test_gates.py::test_apply_answer_with_blank_answer_still_flips_status

Builds the answered form of one operator gate context file from the current file text and the submitted operator answer. The method is a pure text mutation: it does not read or write the workspace volume, does not check whether the gate is still awaiting, and does not clear in-memory dashboard state.

#### Effects

- Reads: the supplied gate file text and submitted answer text only.
- Parses: the first line matching `^STATUS:[ \t]*(\S+)` under multiline parsing as the only status line eligible for replacement.
- Mutates text: replaces at most one matched status line with exactly `STATUS: ANSWERED`; if no line matches, the status portion of the returned text is unchanged.
- Preserves: all unmatched file content, section ordering, headings, and non-status text before any optional answer append.
- Normalizes: strips leading and trailing whitespace from the submitted answer before deciding whether an answer paragraph exists.
- Appends: when the stripped answer is non-empty, right-trims the status-updated file text, adds one blank line, appends the stripped answer, and terminates the file with one newline.
- Skips append: when the stripped answer is empty, returns the status-updated file text without adding an answer paragraph or trimming trailing content.
- Output shape: a non-blank answer always produces text ending with exactly one newline after the answer paragraph; a blank answer preserves whatever trailing whitespace was present after the status replacement.
- Calls: no other groom source symbols.
- Does not mutate: workspace-volume files, Docker containers, workflow containers, in-memory gate records, per-gate answer locks, dashboard websocket queues, sidecar connections, or browser DOM state.

## Lifecycle

- step: A workflow wait script writes a context file with `STATUS: AWAITING_OPERATOR` and enough question/context text for an operator.
- step: The sidecar or host discovery scans workspace files and keeps only files whose status parser returns `AWAITING_OPERATOR` from the scan prefix.
- step: Groom stores the workspace-relative path and extracted question as a gate record and renders an answer form for that specific path.
- step: On answer submission, the gate-answering layer rereads the same file while holding the per-gate lock and rejects it unless the current status is still `AWAITING_OPERATOR`.
- step: The accepted answer changes the status line to `STATUS: ANSWERED` and may append the submitted answer paragraph.
- step: The in-container wait script observes the changed file and proceeds; later non-awaiting statuses are ignored by groom discovery and answer handling.
