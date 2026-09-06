---
type: format
slug: operator-gate-file
title: Operator gate file
---
# Operator gate file

The operator gate is a text file at the path supplied to `Await`. Its first header line is the
authoritative state; the body preserves questions and answer history. Plain questions are
wrapped in a discoverable heading, structured files are re-armed without double-wrapping, and
answers are appended after the existing content.

- file: `<run_dir>/<await path>`
- code: `workhorse/workhorse/gates.py::format_operator_gate`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_gates.py::test_structured_operator_gate_is_rearmed_without_double_wrapping`

## Fields

### STATUS
- type: uppercase token on the first line
- required: true
- semantics: current gate state
- verify: json_path(path="$.status", equals="AWAITING_OPERATOR")
- semantics: an answer is represented by `ANSWERED`
- verify: json_path(path="$.status", equals="ANSWERED")
- semantics: a pending gate is represented by `AWAITING_OPERATOR`
- verify: json_path(path="$.status", equals="AWAITING_OPERATOR")
- code: `workhorse/workhorse/gates.py::status_of`

### SCOPE
- type: lowercase token on its own line
- required: false
- semantics: caller-owned scope vocabulary, returned without engine interpretation
- verify: json_path(path="$.scope", equals="epic")
- code: `workhorse/workhorse/gates.py::scope_of`

### Questions from the agent
- type: markdown section
- required: false
- semantics: human-readable question body shown while the gate is pending
- verify: visible(locator="operator gate question", text="which branch?")
- code: `workhorse/workhorse/gates.py::format_operator_gate`

## Methods

### status_of
- sig: `status_of(text: str) -> str`
- returns: upper-cased STATUS token, or empty string when absent
- verify: json_path(path="$.status", equals="ANSWERED")
- code: `workhorse/workhorse/gates.py::status_of`
- tests: `workhorse/tests/test_gates.py::test_case_is_normalised_in_both_directions`

### scope_of
- sig: `scope_of(text: str) -> str`
- returns: lower-cased SCOPE token, or empty string when absent
- verify: json_path(path="$.scope", equals="epic")
- code: `workhorse/workhorse/gates.py::scope_of`
- tests: `workhorse/tests/test_gates.py::test_status_and_scope_are_read_off_their_own_lines`

### set_status
- sig: `set_status(text: str, status: str) -> str`
- does: replaces only the first STATUS line, or prepends one when absent
- returns: original content preserved except for the live status line
- verify: unchanged(subject="operator gate content except its first STATUS line")
- code: `workhorse/workhorse/gates.py::set_status`
- tests: `workhorse/tests/test_gates.py::test_set_status_rewrites_only_the_first_line`

### format_operator_gate
- sig: `format_operator_gate(questions: str) -> str`
- does: creates a pending header and Questions heading for plain text
- does: re-arms structured content without duplicating its heading
- returns: newline-terminated gate content
- verify: visible(locator="operator gate question", text="which branch?")
- code: `workhorse/workhorse/gates.py::format_operator_gate`
- tests: `workhorse/tests/test_gates.py::test_plain_questions_format_as_a_discoverable_operator_gate`

### apply_answer
- sig: `apply_answer(text: str, answer: str) -> str`
- does: changes the first STATUS to ANSWERED
- does: appends non-empty answer prose after existing content
- returns: durable answered gate content
- verify: persists(subject="answered operator gate")
- code: `workhorse/workhorse/gates.py::apply_answer`
- tests: `workhorse/tests/test_gates.py::test_apply_answer_flips_the_status_and_appends_the_prose`

### append_operator_gate
- sig: `append_operator_gate(existing: str, questions: str) -> str`
- does: re-arms the existing gate and appends a new question block
- does: preserves prior questions and operator answers
- returns: one-status-line gate content with accumulated history
- verify: count(subject="STATUS lines after re-arming a gate with history", equals=1)
- code: `workhorse/workhorse/gates.py::append_operator_gate`
- tests: `workhorse/tests/test_gates.py::test_a_second_ask_keeps_the_first_ones_questions_and_its_answers`
