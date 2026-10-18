---
type: format
slug: settlement
title: Coder finding settlement
---
# Coder finding settlement

One sign-off pass over the filed review findings: which held, which were declined and which stay open.

- file: none — in-memory settlement result
- config: `Settlement` returned by the settle-findings node
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement` @b990c5de7212
- detail: [coder review shared nodes](../concepts/coder-review-shared-review.md)

## Fields

### settled
- type: list of `str`
- default: empty list
- semantics: ids of fixed findings whose cited commits, paths and tests all hold up
- verify: json_path(path="$.settled", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.settled` @b990c5de7212

### declined
- type: list of `str`
- default: empty list
- semantics: ids of findings the owner declined with a reason
- verify: json_path(path="$.declined", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.declined` @b990c5de7212

### open
- type: list of `str`
- default: empty list
- semantics: ids still unanswered, plus fixed ids whose evidence was rejected
- verify: json_path(path="$.open", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.open` @b990c5de7212

### rejected
- type: mapping of finding id to reason
- default: empty mapping
- semantics: why a fixed answer's evidence did not hold up
- verify: json_path(path="$.rejected", matches="^\\{.*\\}$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.rejected` @b990c5de7212

### errors
- type: list of `str`
- default: empty list
- semantics: problems the ledger reported while settling
- verify: json_path(path="$.errors", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Settlement.errors` @b990c5de7212
