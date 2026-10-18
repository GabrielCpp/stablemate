---
type: format
slug: review-finding
title: Coder review finding
---
# Coder review finding

- file: none — in-memory review result member
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding` @818036e1a230
- detail: [coder finding](finding.md)
- detail: [coder review schema contracts](../concepts/coder-review-schema-contracts.md)

`ReviewFinding` extends the shared finding shape with the review lens and a confidence score.
The dev owner's result carries every finding its reviewer reported, verbatim and in order, before
triage drops any.

## Fields

### target
- type: `str`
- default: empty string
- required: false
- semantics: repository-relative location or other target of the review issue
- verify: json_path(path="$.target", equals="src/app.py")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding` @818036e1a230
- detail: [review finding core fields](../concepts/review-finding-core-fields.md)

### issue
- type: `str`
- default: empty string
- required: false
- semantics: problem identified by the review
- verify: json_path(path="$.issue", equals="The check fails on an empty list.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding` @818036e1a230
- detail: [review finding core fields](../concepts/review-finding-core-fields.md)

### repair
- type: `str`
- default: empty string
- required: false
- semantics: smallest change that addresses the review issue
- verify: json_path(path="$.repair", equals="Guard the empty list before reading it.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding` @818036e1a230
- detail: [review finding core fields](../concepts/review-finding-core-fields.md)

### category
- type: literal `Bug`, `Standard`, or `Reuse`
- required: true
- semantics: review lens that found the issue
- verify: json_path(path="$.category", matches="Bug|Standard|Reuse")
- semantics: the `Reuse` lens covers duplication and a missed utility
- verify: json_path(path="$.category", equals="Reuse")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding.category` @818036e1a230

### score
- type: integer from 0 through 100
- default: 0
- required: false
- semantics: reviewer confidence, which the dev reviewer reports only at 80 or higher
- verify: json_path(path="$.score", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding.score` @818036e1a230
