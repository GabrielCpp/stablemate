---
type: format
slug: dev-fix-result
title: Coder dev-fix result
---
# Coder dev-fix result

- file: none — agent reply and checkpoint value
- config: `FixResult` dev-fix turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FixResult`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)
- detail: [coder result routing contract](concepts/coder-result-routing.md)

## Fields

### status
- type: literal `fixed`, `failed`, or `blocked`
- required: true
- semantics: repair outcome reported by the dev-fix turn
- verify: json_path(path="$.status", matches="fixed|failed|blocked")
- semantics: `fixed` reports that the gate passes now in the declared directory, prompting a re-run of the gates without another dev-fix turn
- semantics: `failed` reports that findings remain but another lap over the same output could plausibly close them, prompting a re-run of the gates and another dev-fix turn if the budget remains
- semantics: `blocked` terminates repair laps — the command does not run in this directory at all, the fix demands a behaviour change this stage may not make, or it lives in a repo you were not given — and routes the failure to the implementation operator gate
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FixResult.status`

### notes
- type: `str`
- default: empty string
- required: false
- semantics: what was changed, which finding remains and why, or why repair is blocked
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FixResult.notes`

