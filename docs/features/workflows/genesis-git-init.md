---
type: format
slug: genesis-git-init
title: Genesis Git initialization result
---
# Genesis Git initialization result

- file: none — in-memory genesis result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::GitInit`
- detail: [coder genesis bootstrap](concepts/coder-genesis-bootstrap.md)

The result says whether the target has a committed Git repository and identifies an initial
commit when genesis created one.

## Fields

### ready
- type: boolean
- default: false
- required: false
- semantics: whether the target has a committed repository ready for later steps
- verify: json_path(path="$.ready", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::GitInit.ready`

### note
- type: string
- default: empty string
- required: false
- semantics: explanation of repository creation or reuse
- verify: json_path(path="$.note", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::GitInit.note`

### initial_commit
- type: string
- default: empty string
- required: false
- semantics: identifier of the initial commit when one was created or found
- verify: json_path(path="$.initial_commit", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::GitInit.initial_commit`
