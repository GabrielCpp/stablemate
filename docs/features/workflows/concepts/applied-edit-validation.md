---
type: concept
slug: applied-edit-validation
title: Applied edit validation
---
# Applied edit validation

`validate_applied_edit` is the single post-application validator. For a deleted epic, it confirms
that no epic with the snapshotted identity remains. For a surviving epic, it compares the resulting
seed and story identifiers and metadata with the approved projection, then hashes every unaffected
story body to detect an undeclared prose change.

Use the flow phase when following the epic-edit journey through mutation and its immediate
post-application check. Use the method node when implementing, testing, or diagnosing the callable
validator's `Defects` result. These are two views of the same validator, not alternative
implementations or a ranked choice.

- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_applied_edit`
- rule: follow the flow phase for journey context and the method node for the callable validation contract
