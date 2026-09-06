---
type: format
slug: survey-assessment-prompt
title: Survey assessment prompt contract
---
# Survey assessment prompt contract

- file: `workflows/src/workhorse_workflows/author/surveyor/prompts/assess-unit.md`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitAssessment`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)
- tests: `workflows/tests/author/surveyor/test_flow.py::test_the_assessor_is_handed_the_unit_the_rubric_and_the_context_file`

The assessor examines exactly one frozen inventory unit against the rubric and writes one
finding-record artifact. It must preserve evidence for each finding, use a reusable remediation
pattern, and distinguish an assessable result (`assessed` or `clean`) from a blocked precondition
or a unit that must be split into immediate children.

## Fields

### unit_id
- type: string
- required: true
- semantics: frozen inventory identifier being assessed
- verify: json_path(path="$.unit_id", matches=".+")

### unit_path
- type: string path or locator
- required: true
- semantics: repository-relative source location of the unit
- verify: json_path(path="$.unit_path", matches=".+")

### unit_kind
- type: string
- required: true
- semantics: inventory kind, such as `folder`, `file`, or a command-defined kind
- verify: json_path(path="$.unit_kind", matches=".+")

### record_path
- type: string path
- required: true
- semantics: finding-record Markdown path the assessor must write
- verify: json_path(path="$.record_path", matches=".+")

### rubric
- type: string path
- required: true
- semantics: concern definition and referenced stack-specific assessment guidance
- verify: json_path(path="$.rubric", matches=".+")

### context_path
- type: string path
- required: true
- semantics: operator context whose prior answer must be honored when the unit was previously blocked
- verify: json_path(path="$.context_path", matches=".+")

### status
- type: string
- default: empty string
- required: false
- semantics: `assessed`, `clean`, `split`, or `blocked`; `split` replaces the unit and writes no record
- verify: json_path(path="$.status", matches=".*")

### notes
- type: string
- default: empty string
- required: false
- semantics: concise assessment, split rationale, or blocking explanation
- verify: json_path(path="$.notes", matches=".*")
