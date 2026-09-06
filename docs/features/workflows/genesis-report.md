---
type: format
slug: genesis-report
title: Genesis validation report
---
# Genesis validation report

- file: none — in-memory genesis result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::GenesisReport`
- detail: [coder genesis bootstrap](concepts/coder-genesis-bootstrap.md)

The final genesis report aggregates required-precondition errors and non-fatal warnings. The
main coder flow proceeds only when the report is valid.

## Fields

### valid
- type: boolean
- default: false
- required: false
- semantics: whether every required genesis precondition passed
- verify: json_path(path="$.valid", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::GenesisReport.valid`

### errors
- type: string
- default: empty string
- required: false
- semantics: newline-separated required-precondition failures
- verify: json_path(path="$.errors", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::GenesisReport.errors`

### warnings
- type: string
- default: empty string
- required: false
- semantics: newline-separated non-fatal validation warnings
- verify: json_path(path="$.warnings", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::GenesisReport.warnings`
