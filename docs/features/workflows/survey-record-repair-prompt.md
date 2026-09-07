---
type: format
slug: survey-record-repair-prompt
title: Survey record-repair prompt contract
---
# Survey record-repair prompt contract

- file: `workflows/src/workhorse_workflows/author/surveyor/prompts/fix-record.md`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)
- tests: `workflows/tests/author/surveyor/test_flow.py::test_an_invalid_record_is_repaired_once_and_the_unit_lands_assessed`

The repair turn is mechanical: it receives one invalid finding record and its validator errors,
repairs syntax or field shape in place, and preserves the record's substantive findings. It must
not reassess the unit, soften claims, or remove content; deterministic validation immediately
after the turn remains authoritative. The flow bounds repair attempts and marks the unit blocked
when validation still fails.

## Fields

### record_path
- type: string path
- required: true
- semantics: finding-record Markdown file repaired in place
- verify: json_path(path="$.record_path", matches=".+")

### unit_id
- type: string
- required: true
- semantics: exact inventory identifier the record must continue to describe
- verify: json_path(path="$.unit_id", matches=".+")

### record_errors
- type: string
- required: true
- semantics: validator diagnostics that identify the record shape defects to repair
- verify: json_path(path="$.record_errors", matches=".+")

### status
- type: string
- default: empty string
- required: false
- semantics: advisory reply outcome, `fixed` or `blocked`
- verify: json_path(path="$.status", matches="^(fixed|blocked)$")
- semantics: validation, not this field, decides acceptance
- verify: json_path(path="$.status", matches="^(fixed|blocked)$")

### notes
- type: string
- default: empty string
- required: false
- semantics: concise description of the repair or why no safe repair was possible
- verify: json_path(path="$.notes", matches=".*")
