---
type: concept
slug: coder-fix-ci-package
title: Coder fix-ci package
---
# Coder fix-ci package

The `fix-ci` machine checks the configured epic branch in workspace repositories against CI
gates and repairs failures. It is a sub-flow entered by the Coder main flow after story
implementation and documentation pass, and can also be run directly with `workhorse-coder run fix-ci`.

The flow polls CI for each repository branch, accumulates failed checks, and offers bounded repair
cycles for each failure. Repositories are processed in manifest order, and gate failures are
persisted for operator inspection when repair exhausts its budget. The flow returns all CI
remediation results collected during the run.

- code: `workflows/src/workhorse_workflows/coder/fix_ci/flow.py`
- code: `workflows/src/workhorse_workflows/coder/fix_ci/flow.py::FixCi`
- tests: `workflows/tests/coder/test_fix_ci.py`
- detail: [CI gating helpers](ci-gating.md)

