---
type: format
slug: ci-checks
title: CI check verdict
---
# CI check verdict

The result of polling one pull request's GitHub Actions runs is either passed, failed,
unavailable, or blocked, with a summary forwarded to the fixer or terminal result.

- file: none — this is an in-memory node result, not a persisted file format
- config: none — polling cadence is an argument to the polling node
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiChecks`
- detail: [coder CI remediation flow](flows/fix-ci-remediation.md)
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_every_workspace_repo_is_checked_once_and_the_loop_ends`

## Fields

### status

- type: `Literal["passed", "failed", "unavailable", "blocked"]`
- default: `failed`
- required: false
- semantics: `passed` means at least one Actions run existed and every run succeeded
- verify: json_path(path="$.status", equals="passed")
- semantics: `failed` means a settled run failed or the watch timed out before runs settled
- verify: json_path(path="$.status", equals="failed")
- semantics: `unavailable` means there was no CI surface to read
- verify: json_path(path="$.status", equals="unavailable")
- semantics: `blocked` means CI existed but GitHub refused or could not provide the required data
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiChecks.status`

### summary

- type: `str`
- default: empty string
- required: false
- semantics: on `failed`, names failing workflows and includes their run ids when available
- verify: json_path(path="$.summary", matches="/.+#\\d+/")
- semantics: on `unavailable`, states that no CI surface was available to read
- verify: json_path(path="$.summary", matches="/.+/")
- semantics: on `blocked`, states why the available CI surface was not readable
- verify: json_path(path="$.summary", matches="/.+/")
- semantics: on `passed`, states that all observed Actions runs succeeded
- verify: json_path(path="$.summary", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiChecks.summary`
