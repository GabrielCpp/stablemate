---
type: format
slug: ledger
title: Author attempt ledger
---
# Author attempt ledger

The rework ledger carries prior attempts and the accumulated failed approaches so the next prompt
does not repeat them.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Ledger`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### prior_attempts
- type: string
- default: empty string
- required: false
- semantics: prior-attempt text read before the current rework pass
- verify: json_path(path="$.prior_attempts", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Ledger`

### ledger
- type: string
- default: empty string
- required: false
- semantics: accumulated failed approaches passed to the rework prompt
- verify: json_path(path="$.ledger", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Ledger`
