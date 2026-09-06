---
type: format
slug: ci-flagged
title: CI failure flag result
---
# CI failure flag result

- file: none — an in-memory result returned after optional PR notification
- config: none — its value is produced by the CI failure flagging node
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::CiFlagged`
- detail: [coder main PR boundary](concepts/coder-main-pr-boundary.md)

The result records whether the operator-facing CI failure note was posted. A false result is also
the expected outcome when no usable credential, repository, or open PR exists.

## Fields

### ci_flagged

- type: `bool`
- default: `false`
- required: false
- semantics: whether the CI failure note was successfully posted to the open epic pull request
- verify: json_path(path="$.ci_flagged", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::CiFlagged.ci_flagged`
