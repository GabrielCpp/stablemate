---
type: format
slug: coder-apply-review-prompt
title: Coder apply-review prompt
---
# Coder apply-review prompt

- file: `workflows/src/workhorse_workflows/coder/review/prompts/apply-review.md`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`
- detail: [coder review flow](flows/coder-review.md)
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)
- tests: `workflows/tests/coder/review/test_flow.py::test_the_apply_loop_is_bounded_and_then_reaches_the_operator`

The apply turn is limited to the supplied story and review or operator feedback. It must resolve
only required findings, preserve story scope, update tests for behavior changes, and write
`review-resolution.json`. The deterministic settlement gate, not the turn's returned status,
decides whether each cited artifact or exact JSON assertion proves a finding; unresolved work is
re-applied or blocked according to the flow.

## Fields

### story_path
- type: `str path`
- required: true
- semantics: the only story document the turn may modify
- verify: json_path(path="$.story_path", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`

### spec_dir
- type: `str path`
- required: true
- semantics: directory containing review.md and the required review-resolution.json sidecar
- verify: json_path(path="$.spec_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`

### review_notes
- type: `str`
- required: true
- semantics: implementation-review findings to resolve; empty when operator feedback is the work
- verify: json_path(path="$.review_notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`

### operator_feedback
- type: `str`
- default: empty string
- required: false
- semantics: human feedback applied within the existing story scope, when supplied
- verify: json_path(path="$.operator_feedback", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply_resolved`

### status
- type: `Literal[done, applied, no_changes_needed, needs_changes, blocked]`
- required: true
- semantics: turn-reported application result; the review flow does not trust it until settlement verifies the sidecar
- verify: json_path(path="$.status", matches="^(done|applied|no_changes_needed|needs_changes|blocked)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplResult.status`

### notes
- type: `str`
- default: empty string
- required: false
- semantics: brief describing what the apply turn changed or why it could not act
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplResult.notes`

## Fields: review-resolution.json finding

### id
- type: `str`
- required: true
- semantics: exact finding identifier from review.md
- verify: json_path(path="$.findings", matches=".*")

### disposition
- type: `Literal[addressed, blocked]`
- required: true
- semantics: whether the finding has been fixed with proof or cannot be resolved in scope
- verify: json_path(path="$.findings", matches=".*")

### artifacts
- type: `list[str path]`
- default: empty list
- required: false
- semantics: paths relative to spec_dir containing proof artifacts that exist on disk
- verify: json_path(path="$.findings", matches=".*")

### assertions
- type: `list[{file, pointer, equals}]`
- default: empty list
- required: false
- semantics: exact JSON value checks against files on disk used as settlement proof
- verify: json_path(path="$.findings", matches=".*")
