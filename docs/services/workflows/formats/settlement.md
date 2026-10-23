---
type: format
slug: settlement
title: Coder finding settlement
---
# Coder finding settlement

One sign-off pass over the filed review findings: which held, which were declined and which stay open.

- file: none — in-memory settlement result
- config: `Settlement` returned by the settle-findings node
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement` @66a3da11dcb2
- detail: [coder review shared nodes](../concepts/coder-review-shared-review.md)

## Fields

### settled
- type: list of `str`
- default: empty list
- semantics: ids of fixed findings whose cited commits, paths and tests all hold up
- verify: json_path(path="$.settled", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.settled` @66a3da11dcb2

### declined
- type: list of `str`
- default: empty list
- semantics: ids of findings the owner declined with a reason, where a "not a defect" decline also names a test that exists
- verify: json_path(path="$.declined", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.declined` @66a3da11dcb2

### open
- type: list of `str`
- default: empty list
- semantics: ids still unanswered, plus the ids whose answer was rejected
- verify: json_path(path="$.open", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.open` @66a3da11dcb2

### rejected
- type: mapping of finding id to reason
- default: empty mapping
- semantics: why a fixed answer's evidence, or a "not a defect" decline's test, did not hold up
- verify: json_path(path="$.rejected", matches="^\\{.*\\}$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.rejected` @66a3da11dcb2

### errors
- type: list of `str`
- default: empty list
- semantics: problems the ledger reported while settling
- verify: json_path(path="$.errors", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.errors` @66a3da11dcb2
