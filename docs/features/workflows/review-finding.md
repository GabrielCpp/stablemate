---
type: format
slug: review-finding
title: Coder review finding
---
# Coder review finding

- file: none — in-memory review result member
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding`
- detail: [coder finding](finding.md)
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)

`ReviewFinding` extends the shared finding shape with the review lens and a confidence score.
The review flow keeps every finding; confidence controls whether it is mandatory or advisory.

## Fields

### target
- type: `str`
- default: empty string
- required: false
- semantics: repository-relative location or other target of the review issue
- verify: json_path(path="$.target", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding`

### issue
- type: `str`
- default: empty string
- required: false
- semantics: problem identified by the review
- verify: json_path(path="$.issue", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding`

### repair
- type: `str`
- default: empty string
- required: false
- semantics: smallest change that addresses the review issue
- verify: json_path(path="$.repair", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding`

### category
- type: literal `Bug`, `Standard`, or `Reuse`
- required: true
- semantics: review lens that found the issue; `Reuse` covers duplication and a missed utility
- verify: json_path(path="$.category", matches="Bug|Standard|Reuse")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding.category`
- tests: `workflows/tests/coder/review/test_flow.py::test_the_split_is_inclusive_at_the_confidence_line`

### score
- type: integer from 0 through 100
- default: 0
- required: false
- semantics: reviewer confidence used to split mandatory findings at 80 or higher from advisory findings
- verify: json_path(path="$.score", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding.score`
