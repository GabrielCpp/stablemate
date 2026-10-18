---
type: format
slug: fix-ci-result
title: CI fixer result
---
# CI fixer result

The structured report returned by the `fix-ci` agent turn describes whether it repaired the
failing branch, could not repair this attempt, or is blocked by a dependency the repository cannot
change. The flow acts only on `blocked`; the next poll judges `fixed` and `failed`.

- file: none — the report is an agent response, not a persisted file format
- config: none — its values come from the prompt output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::FixCiResult` @3939e8547cf4
- detail: [coder CI remediation flow](../flows/fix-ci-remediation.md)

## Fields

### status

- type: `Literal["fixed", "failed", "blocked"]`
- default: none
- required: true
- semantics: `fixed` claims that the failure was repaired locally
- verify: json_path(path="$.status", equals="fixed")
- semantics: `fixed` claims that the local repair was committed
- semantics: `failed` says the failure was understood but this attempt did not repair it
- verify: json_path(path="$.status", equals="failed")
- semantics: `failed` permits the flow to retry the fixer
- semantics: `blocked` says another attempt cannot make CI green without an unavailable dependency
- verify: json_path(path="$.status", equals="blocked")
- semantics: `blocked` says the required change would alter an observable contract outside this stage's scope
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::FixCiResult.status` @3939e8547cf4

### notes

- type: `str`
- default: empty string
- required: false
- semantics: for `fixed`, notes describe the changes made
- verify: json_path(path="$.notes", matches="/.+/")
- semantics: for `failed`, notes describe what was attempted
- semantics: for `failed`, notes explain why the attempt did not repair CI
- semantics: for `blocked`, notes identify the unavailable dependency
- semantics: for `blocked`, notes name the question whose answer would unblock the fixer
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- semantics: for `blocked`, notes identify the forbidden contract change when that is the blocker
- verify: json_path(path="$.notes", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::FixCiResult.notes` @3939e8547cf4
