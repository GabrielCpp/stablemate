---
type: format
slug: qa-setup-result
title: QA setup repair result
---
# QA setup repair result

The verdict `setup-fix.md` reports on the attempt to repair the QA environment so it becomes capable of running tests.

- file: none — agent reply and checkpoint value
- config: `SetupResult` agent-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::SetupResult`
- detail: [coder QA schema contracts](concepts/coder-qa-schema-contracts.md)

## Fields

### status

- type: literal `ready` or `unfixable`
- required: true
- semantics: `ready` when the environment is QA-capable — services up and verified, tools installed
- verify: json_path(path="$.status", equals="ready")
- semantics: `ready` also when the blocker is not an environment problem at all, so QA re-runs and routes it to code-fix
- verify: json_path(path="$.status", equals="ready")
- semantics: `unfixable` only for a true wall that needs a human
- verify: json_path(path="$.status", equals="unfixable")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::SetupResult.status`

### notes

- type: `str`
- default: empty string
- required: false
- semantics: what was blocking QA, what was changed or started to fix it, and the readiness proof
- verify: json_path(path="$.notes", matches=".*")
- semantics: when unfixable, exactly which human-only resource is needed
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::SetupResult.notes`

