---
type: format
slug: review-verdict
title: Coder review verdict
---
# Coder review verdict

- file: none — in-memory agent reply
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewVerdict`
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)
- detail: [coder review flow](flows/coder-review.md)

The binding review verdict decides whether implementation proceeds, returns to the apply loop, or
requires an operator because the missing evidence or decision is outside the repository.

## Fields

### status
- type: literal `approved`, `needs_changes`, or `blocked`
- required: true
- semantics: binding implementation verdict
- verify: json_path(path="$.status", matches="approved|needs_changes|blocked")
- semantics: only `approved` proceeds to feedback
- verify: json_path(path="$.status", equals="approved")
- semantics: `needs_changes` supplies notes to the apply loop
- verify: json_path(path="$.status", equals="needs_changes")
- semantics: `blocked` bypasses repair and goes to operator resolution
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewVerdict.status`
- detail: [review verdict status roles](concepts/review-verdict-status-roles.md)

### notes
- type: `str`
- default: empty string
- required: false
- semantics: concise findings brief for repair, or the external dependency and attempted resolution for a block
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewVerdict.notes`
- tests: `workflows/tests/coder/review/test_flow.py::test_an_approved_review_stamps_the_specs_and_stops`
- detail: [review verdict notes context](concepts/review-verdict-notes-context.md)
