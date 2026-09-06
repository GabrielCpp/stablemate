---
type: format
slug: ci-repo-pick
title: CI repository selection
---
# CI repository selection

The selection result identifies whether a workspace repository was found, its name and checkout,
and the updated processed list. A named repository absent from the workspace yields no pick rather
than a failure.

- file: none — this is an in-memory node result
- config: none — selection is derived from workflow inputs and the workspace manifest
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`
- detail: [coder CI remediation flow](flows/fix-ci-remediation.md)

## Fields

### has_repo

- type: `bool`
- default: `false`
- required: false
- semantics: whether `start` has a repository to process
- verify: json_path(path="$.has_repo", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`

### repo

- type: `str`
- default: empty string
- required: false
- semantics: selected workspace repository key
- verify: json_path(path="$.repo", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`

### repo_cwd

- type: `str`
- default: empty string
- required: false
- semantics: selected repository checkout passed to CI polling and the fixer
- verify: json_path(path="$.repo_cwd", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`

### processed

- type: `list[str]`
- default: empty list
- required: false
- semantics: processed repository keys including the newly selected repository
- verify: count(subject="selected repository processing list", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`
