---
type: concept
slug: coder-fix-ci-package
title: Coder fix-ci package
---
# Coder fix-ci package

The `fix-ci` machine checks the configured epic branch in workspace repositories against CI
gates and repairs failures. It is a sub-flow entered by the Coder main flow in its ship lane, and can also be run directly with `workhorse-coder run fix-ci`.

The flow polls CI for each repository branch, runs bounded owner repair turns for each failure,
and merges the epic's pull request once every repository is read when it is given a base.
Repositories are processed in manifest order, and a block that the resolver cannot answer is
persisted as an operator gate. The flow returns the last CI verdict with a summary of the run.

- code: `workflows/src/workhorse_workflows/coder/fix_ci/flow.py` @a7b37f93a2e9
- code: `workflows/src/workhorse_workflows/coder/fix_ci/flow.py::FixCi` @a7b37f93a2e9
- detail: [CI gating helpers](ci-gating.md)

