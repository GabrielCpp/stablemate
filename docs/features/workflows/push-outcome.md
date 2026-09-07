---
type: format
slug: push-outcome
title: CI fix push outcome
---
# CI fix push outcome

The push node reports whether the selected branch was verified on the remote, was unavailable to
push, or failed after an attempted push. Notes identify the branch and local checkout.

- file: none — this is an in-memory node result
- config: none — the outcome is derived from the selected checkout and branch
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::PushOutcome`
- detail: [coder CI remediation flow](flows/fix-ci-remediation.md)
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_push_that_does_not_land_ends_the_loop_instead_of_spending_an_attempt`

## Fields

### status

- type: `Literal["pushed", "unavailable", "failed"]`
- default: `failed`
- required: false
- semantics: `pushed` means the remote head advanced to the local branch
- verify: json_path(path="$.status", equals="pushed")
- semantics: `unavailable` means no push was possible because a required branch, credential, or remote was absent
- verify: json_path(path="$.status", equals="unavailable")
- semantics: `failed` means an attempted push did not land or its remote head could not be verified
- verify: json_path(path="$.status", equals="failed")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::PushOutcome`
- detail: [push outcome field roles](concepts/push-outcome-field-roles.md)

### notes

- type: `str`
- default: empty string
- required: false
- semantics: identifies the status, branch, and checkout context returned with the push outcome
- verify: json_path(path="$.notes", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::PushOutcome`
- detail: [push outcome field roles](concepts/push-outcome-field-roles.md)
