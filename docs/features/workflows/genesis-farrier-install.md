---
type: format
slug: genesis-farrier-install
title: Genesis Farrier installation result
---
# Genesis Farrier installation result

- file: none — in-memory genesis result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::FarrierInstall`
- detail: [coder genesis bootstrap](concepts/coder-genesis-bootstrap.md)

The result records whether Farrier setup completed and which requested scaffolds were rendered
before any failure.

## Fields

### ok
- type: boolean
- default: false
- required: false
- semantics: whether pack installation and requested scaffold rendering succeeded
- verify: json_path(path="$.ok", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::FarrierInstall.ok`

### note
- type: string
- default: empty string
- required: false
- semantics: installation or scaffold explanation
- verify: json_path(path="$.note", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::FarrierInstall.note`

### scaffolds_rendered
- type: list of strings
- default: empty list
- required: false
- semantics: scaffold identifiers rendered in input order
- verify: count(subject="scaffolds_rendered", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::FarrierInstall.scaffolds_rendered`
