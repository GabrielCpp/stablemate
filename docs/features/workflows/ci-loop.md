---
type: format
slug: ci-loop
title: CI remediation loop state
---
# CI remediation loop state

The checkpointed value carried by all four `FixCi` states identifies the selected repository,
its checkout, the repositories already picked, the lifetime fix count, and repositories whose CI
was never readable.

- file: none — this is an in-memory checkpoint value, not a persisted file format
- config: none — the value has no separate configuration file
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop`
- detail: [coder CI remediation flow](flows/fix-ci-remediation.md)
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_the_attempt_budget_is_shared_across_repos_not_reset_per_repo`

## Fields

### repo

- type: `str`
- default: empty string
- required: false
- semantics: workspace key of the repository currently being gated
- verify: json_path(path="$.repo", equals="api")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.repo`

### repo_dir

- type: `str`
- default: empty string
- required: false
- semantics: checkout path passed to every CI node and to the fixer turn
- verify: json_path(path="$.repo_dir", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.repo_dir`

### processed

- type: `list[str]`
- default: empty list
- required: false
- semantics: repositories marked picked so the outer loop visits each at most once
- verify: count(subject="processed CI repositories", equals=2)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.processed`

### attempts

- type: `int`
- default: `0`
- required: false
- semantics: fix/push cycles spent across all repositories and never reset when the outer loop advances
- verify: json_path(path="$.attempts", equals=3)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.attempts`

### unread

- type: `list[str]`
- default: empty list
- required: false
- semantics: `<repo>: <reason>` entries included in the terminal summary when CI was unavailable
- verify: count(subject="unread CI repositories", equals=2)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::CiLoop.unread`
