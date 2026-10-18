---
type: format
slug: ci-loop
title: CI remediation loop state
---
# CI remediation loop state

The checkpointed value carried by all four `FixCi` states identifies the selected repository,
its checkout, the repositories already picked, the lap count for the current repository, the merge state, and repositories
whose CI was never readable.

- file: none — this is an in-memory checkpoint value, not a persisted file format
- config: none — the value has no separate configuration file
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop` @3939e8547cf4
- detail: [coder CI remediation flow](../flows/fix-ci-remediation.md)
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_each_repo_gets_its_own_lap_budget`

## Fields

### repo

- type: `str`
- default: empty string
- required: false
- semantics: workspace key of the repository currently being gated
- verify: json_path(path="$.repo", equals="api")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.repo` @3939e8547cf4

### repo_dir

- type: `str`
- default: empty string
- required: false
- semantics: checkout path passed to every CI node and to the fixer turn
- verify: json_path(path="$.repo_dir", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.repo_dir` @3939e8547cf4

### processed

- type: `list[str]`
- default: empty list
- required: false
- semantics: repositories marked picked so the outer loop visits each at most once
- verify: count(subject="processed CI repositories", equals=2)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.processed` @3939e8547cf4

### laps

- type: `int`
- default: `0`
- required: false
- semantics: fix/push laps spent on the current repository, reset to zero when the outer loop picks the next one
- verify: json_path(path="$.laps", equals=3)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.laps` @3939e8547cf4

### unread

- type: `list[str]`
- default: empty list
- required: false
- semantics: `<repo>: <reason>` entries included in the terminal summary when CI was unavailable
- verify: count(subject="unread CI repositories", equals=2)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.unread` @3939e8547cf4

### merging

- type: `bool`
- default: `false`
- required: false
- semantics: true once every repository has been picked and the loop is merging the epic branch
- verify: json_path(path="$.merging", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.merging` @3939e8547cf4

### merges

- type: `int`
- default: `0`
- required: false
- semantics: merge attempts spent on the epic branch, held against the same lap cap and reset to zero when an operator answer resumes the merge
- verify: json_path(path="$.merges", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.merges` @3939e8547cf4
