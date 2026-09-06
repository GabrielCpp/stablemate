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
- semantics: `passed` means all settled Actions runs succeeded; `failed` means a settled run failed or polling timed out; `unavailable` means there was no CI to read; `blocked` means CI existed but could not be read
- verify: json_path(path="$.status", equals="passed")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiChecks.status`

### summary

- type: `str`
- default: empty string
- required: false
- semantics: failing workflow names and run ids, or the reason CI was passed through or blocked
- verify: json_path(path="$.summary", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiChecks.summary`
