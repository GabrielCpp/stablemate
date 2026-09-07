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
- semantics: complete attempt-ledger text supplied to the rework prompt before the current pass
- verify: json_path(path="$.prior_attempts", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Ledger`
- detail: [attempt ledger field roles](concepts/attempt-ledger-field-roles.md)

### ledger
- type: string
- default: empty string
- required: false
- semantics: repository-relative path of the attempt ledger that `record_attempt` reads or updates
- verify: json_path(path="$.ledger", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Ledger`
- detail: [attempt ledger field roles](concepts/attempt-ledger-field-roles.md)
