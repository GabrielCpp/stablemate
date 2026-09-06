---
type: format
slug: coder-review-implementation-prompt
title: Coder review-implementation prompt
---
# Coder review-implementation prompt

- file: `workflows/src/workhorse_workflows/coder/review/prompts/review-implementation.md`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.review`
- detail: [coder review flow](flows/coder-review.md)
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)
- tests: `workflows/tests/coder/review/test_flow.py::test_the_implementation_reviewer_is_handed_both_feeder_verdicts`

The binding reviewer compares the story, plan, changed repositories, and installed standards.
It receives mandatory findings already split by the flow at confidence 80 and receives all lower
confidence findings as advisory context. It folds the automated findings into its own review,
writes the review artifact and reviewed story status, and returns a verdict. Only Critical or
Major findings require changes; a blocked verdict means the decision cannot be reached from the
available repository and story context.

## Fields

### story_path
- type: `str path`
- required: true
- semantics: story document defining the implementation scope and acceptance criteria
- verify: json_path(path="$.story_path", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.review`

### spec_dir
- type: `str path`
- required: true
- semantics: directory containing the implementation plan and receiving review artifacts
- verify: json_path(path="$.spec_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.review`

### affected_repo_paths
- type: `list[str path]`
- required: true
- semantics: repositories whose implementation and tests are compared with the story
- verify: json_path(path="$.affected_repo_paths", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.review`

### must_fix_findings
- type: `str markdown`
- required: true
- semantics: rendered findings scored at least 80, including their category, target, issue, and required repair
- verify: json_path(path="$.must_fix_findings", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::findings_block`

### advisory_findings
- type: `str markdown`
- required: true
- semantics: rendered findings scored below 80; they inform judgement but cannot by themselves require changes
- verify: json_path(path="$.advisory_findings", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::findings_block`

### status
- type: `Literal[approved, needs_changes, blocked]`
- required: true
- semantics: approval when no Critical or Major finding remains, required changes when one exists, or an external block
- verify: json_path(path="$.status", matches="^(approved|needs_changes|blocked)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewVerdict.status`

### notes
- type: `str`
- default: empty string
- required: false
- semantics: brief covering automated, reuse, and self-review findings, including required repairs or the block reason
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewVerdict.notes`
