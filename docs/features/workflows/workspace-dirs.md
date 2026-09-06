---
type: format
slug: workspace-dirs
title: Workflow workspace directories
---
# Workflow workspace directories

The setup result lists every directory the CI fixer may read: the documentation root followed by
the selected workspace repository directories. It is carried into the agent turn as an explicit
read set.

- file: none — this is an in-memory node result, not a persisted file format
- config: none — the directories are derived from workflow inputs and workspace resolution
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::WorkspaceDirs`
- detail: [coder CI remediation flow](flows/fix-ci-remediation.md)
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_red_branch_is_fixed_pushed_and_re_polled_until_it_is_green`

## Fields

### dirs

- type: `list[str]`
- default: empty list
- required: false
- semantics: ordered absolute directories exposed to the fixer, with the docs root prepended when it is not already present
- verify: count(subject="fixer readable directories", equals=3)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::WorkspaceDirs.dirs`
