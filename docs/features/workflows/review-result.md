---
type: format
slug: review-result
title: Coder review result
---
# Coder review result

- file: none — in-memory flow return value
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewResult`
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)
- detail: [coder review flow](flows/coder-review.md)

The review flow returns this value after approval or verified settlement and after its final inbox
poll. The caller does not branch on a status; the notes field records the flow's brief.

## Fields

### notes
- type: `str`
- default: empty string
- required: false
- semantics: review-flow notes handed to the caller after completion
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewResult.notes`
- tests: `workflows/tests/coder/review/test_flow.py::test_an_approved_review_stamps_the_specs_and_stops`
