---
type: format
slug: survey-operator-diagnosis-prompt
title: Survey operator-diagnosis prompt contract
---
# Survey operator-diagnosis prompt contract

- file: `workflows/src/workhorse_workflows/author/surveyor/prompts/resolve-operator.md`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)
- tests: `workflows/tests/author/surveyor/test_flow.py::test_human_operator_mode_sends_the_block_straight_to_the_context_file`

The diagnostic investigator receives a blocked plan, coverage, or partition stage and briefs the
human operator. It reads the operator context first, investigates the blocking evidence with full
tool access, and appends findings without deciding scope, changing inventory status, or editing
rules or partition artifacts. The response always escalates; the workflow parks in `Await` and
only a human answer can resume it.

## Fields

### node_timeout_min
- type: number or `unbounded`
- required: true
- semantics: investigation time budget
- verify: json_path(path="$.node_timeout_min", matches=".+")
- semantics: survey resolver turns use an unbounded timeout
- verify: json_path(path="$.node_timeout_min", equals="unbounded")

### block_stage
- type: string
- required: true
- semantics: blocked stage, one of `plan-units`, `survey-coverage`, or `partition`
- verify: json_path(path="$.block_stage", matches=".+")

### survey_dir
- type: string path
- required: true
- semantics: directory containing rules, inventory, records, partition, and context artifacts
- verify: json_path(path="$.survey_dir", matches=".+")

### context_path
- type: string path
- required: true
- semantics: operator context file whose existing history is preserved and whose first status line is re-armed
- verify: json_path(path="$.context_path", matches=".+")

### block_notes
- type: string
- required: true
- semantics: producer's blocking question or validation diagnostics to investigate
- verify: json_path(path="$.block_notes", matches=".+")

### decision
- type: string
- default: empty string
- required: false
- semantics: compatibility reply field retained for the response shape
- verify: json_path(path="$.decision", matches=".*")
- semantics: resolver emits `escalated` as an advisory value that the flow ignores for branching
- verify: json_path(path="$.decision", equals="escalated")

### notes
- type: string
- default: empty string
- required: false
- semantics: one-line plain-language statement of the unresolved operator decision
- verify: json_path(path="$.notes", matches=".+")

### tried
- type: list[string]
- default: empty list
- required: false
- semantics: concrete investigations and ruled-out hypotheses, one line per checked item
- verify: json_path(path="$.tried", matches=".*")
