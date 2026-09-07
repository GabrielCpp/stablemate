---
type: concept
slug: ci-repo-pick-field-roles
title: CI repository selection field roles
---
# CI repository selection field roles

`CiRepoPick` carries one selection result, not four alternative selection mechanisms. `has_repo`
is the outcome gate: consumers must inspect it before using a selected repository. When it is
true, `repo` identifies the workspace key and `repo_cwd` identifies that repository's checkout.
`processed` is the separate loop accumulator: the selector appends a repository as soon as it
picks it so a later pass skips it regardless of its CI result.

No field supersedes or ranks above another. They have distinct roles and are read together for a
successful selection; when no repository is available, `has_repo` records that outcome while the
other fields do not represent an alternative pick.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiRepoPick`
- rule: inspect `has_repo` to determine whether a selection exists; use `repo` and `repo_cwd` only for that selection, and retain `processed` as the history that prevents reselection
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_every_workspace_repo_is_checked_once_and_the_loop_ends`
