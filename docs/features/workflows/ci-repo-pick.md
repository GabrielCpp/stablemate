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
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_every_workspace_repo_is_checked_once_and_the_loop_ends`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_named_repo_pins_the_loop_to_that_one`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_repo_absent_from_the_workspace_is_a_warning_not_a_failure`

## Fields

### has_repo

- type: `bool`
- default: `false`
- required: false
- semantics: `true` means the selection has a repository for `start` to process
- verify: json_path(path="$.has_repo", equals=true)
- semantics: `false` means the named repository was absent when a name was requested
- verify: json_path(path="$.has_repo", equals=false)
- semantics: `false` means every workspace repository was already processed when no pick remained
- verify: json_path(path="$.has_repo", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`
- detail: [CI repository selection field roles](concepts/ci-repo-pick-field-roles.md)

### repo

- type: `str`
- default: empty string
- required: false
- semantics: selected workspace repository key
- verify: json_path(path="$.repo", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`
- detail: [CI repository selection field roles](concepts/ci-repo-pick-field-roles.md)

### repo_cwd

- type: `str`
- default: empty string
- required: false
- semantics: selected repository checkout passed to CI polling and the fixer
- verify: json_path(path="$.repo_cwd", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`
- detail: [CI repository selection field roles](concepts/ci-repo-pick-field-roles.md)

### processed

- type: `list[str]`
- default: empty list
- required: false
- semantics: contains the repository keys already selected by earlier passes
- verify: json_path(path="$.processed", matches="/.*/")
- semantics: when `has_repo` is true, includes the newly selected repository
- verify: json_path(path="$.processed", matches="/.*/")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`
- detail: [CI repository selection field roles](concepts/ci-repo-pick-field-roles.md)
