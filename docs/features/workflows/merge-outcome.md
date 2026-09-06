---
type: format
slug: merge-outcome
title: Merge outcome result
---
# Merge outcome result

- file: none — an in-memory result returned between coder workflow nodes
- config: none — its values are produced by the merge operation
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::MergeOutcome`
- detail: [coder main PR boundary](concepts/coder-main-pr-boundary.md)

The result distinguishes a landed merge from a merge that could not be attempted and one that was
attempted but failed. Python defaults an unanswered result to the pessimistic `failed` arm.

## Fields

### merge_status

- type: `Literal["merged", "unavailable", "failed"]`
- default: `failed`
- required: false
- semantics: `merged` means the epic branch landed
- semantics: `unavailable` means no usable remote operation or open PR existed
- semantics: `failed` means a merge was attempted and did not land
- verify: json_path(path="$.merge_status", equals="failed")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::MergeOutcome.merge_status`

### base_branch

- type: `str`
- default: empty string
- required: false
- semantics: the base branch targeted by the merge attempt
- verify: json_path(path="$.base_branch", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::MergeOutcome.base_branch`
