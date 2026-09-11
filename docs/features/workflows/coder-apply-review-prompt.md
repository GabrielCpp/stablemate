---
type: format
slug: coder-apply-review-prompt
title: Coder apply-review prompt
---
# Coder apply-review prompt

- file: `workflows/src/workhorse_workflows/coder/review/prompts/apply-review.md`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`
- code: `workflows/tests/coder/test_status_line_ownership.py::test_the_prompt_forbids_writing_the_story_status_line`
- code: `workflows/tests/coder/test_status_line_ownership.py::test_the_guard_names_what_enforces_it`
- detail: [coder review flow](flows/coder-review.md)
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)
- detail: [coder story status check](story-status-check.md)
- tests: `workflows/tests/coder/review/test_flow.py::test_the_apply_loop_is_bounded_and_then_reaches_the_operator`
- tests: `workflows/tests/coder/test_status_line_ownership.py::test_the_prompt_forbids_writing_the_story_status_line`
- tests: `workflows/tests/coder/test_status_line_ownership.py::test_the_guard_names_what_enforces_it`

The apply turn is limited to the supplied story and review or operator feedback. It must resolve
only required findings, preserve story scope, update tests for behavior changes, and write
`review-resolution.json`. The deterministic settlement gate, not the turn's returned status,
decides whether each cited artifact or exact JSON assertion proves a finding; unresolved work is
re-applied or blocked according to the flow.

The prompt carries a `## Story Status` section that names the story's `Implementation Status`
field and prohibits the turn from editing it. Unlike `implement-plan`, this lane owns the
transition out of review (the `settle-review` gate sets the line from the structured verdict), so
the prohibition names the gate as the writer rather than as a re-reader; the contract the test
verifies is the same shape — the prohibition must name the machinery, never stand as a bare rule.

## Fields

### story_path
- type: `str path`
- required: true
- semantics: the only story document the turn may modify
- verify: json_path(path="$.story_path", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`
- detail: [review apply turn inputs](concepts/review-apply-turn-inputs.md)

### spec_dir
- type: `str path`
- required: true
- semantics: directory containing review.md and the required review-resolution.json sidecar
- verify: json_path(path="$.spec_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`
- detail: [review apply turn inputs](concepts/review-apply-turn-inputs.md)

### review_notes
- type: `str`
- required: true
- semantics: implementation-review findings to resolve when findings are supplied
- verify: json_path(path="$.review_notes", matches=".*")
- semantics: empty when operator feedback is the work
- verify: json_path(path="$.review_notes", equals="")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`
- detail: [review apply turn inputs](concepts/review-apply-turn-inputs.md)

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
- semantics: turn-reported application result
- verify: json_path(path="$.status", matches="^(done|applied|no_changes_needed|needs_changes|blocked)$")
- semantics: review flow accepts the application result only after settlement verifies the sidecar
- verify: json_path(path="$.status", matches="^(done|applied|no_changes_needed|needs_changes|blocked)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplResult.status`
- detail: [implementation result status](concepts/implementation-result-status.md)

### notes
- type: `str`
- default: empty string
- required: false
- semantics: brief describing what the apply turn changed or why it could not act
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplResult.notes`
- detail: [implementation result notes](concepts/impl-result-notes.md)

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
