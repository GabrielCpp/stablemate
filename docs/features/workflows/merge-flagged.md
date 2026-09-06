---
type: format
slug: merge-flagged
title: Merge failure flag result
---
# Merge failure flag result

- file: none — an in-memory result returned after optional PR notification
- config: none — its value is produced by the merge failure flagging node
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::MergeFlagged`
- detail: [coder main PR boundary](concepts/coder-main-pr-boundary.md)

The result records whether the operator-facing merge failure note was posted. A false result is
also the expected outcome when no usable credential, repository, or open PR exists.

## Fields

### merge_flagged

- type: `bool`
- default: `false`
- required: false
- semantics: whether the merge failure note was successfully posted to the open epic pull request
- verify: json_path(path="$.merge_flagged", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::MergeFlagged.merge_flagged`
