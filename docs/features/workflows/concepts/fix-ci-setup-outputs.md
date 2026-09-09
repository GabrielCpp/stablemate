---
type: concept
slug: fix-ci-setup-outputs
title: Coder CI remediation setup outputs
---
# Coder CI remediation setup outputs

[`setup`](../flows/fix-ci-remediation.md#setup) and [`start`](../flows/fix-ci-remediation.md#start)
are two sequential steps of the same [CI remediation flow](../flows/fix-ci-remediation.md), and
each carries its own result: `setup` runs once and resolves the
[workspace directory set](../workspace-dirs.md) an agent turn may read; `start` runs once per
loop pass and resolves the [CI repository selection](../ci-repo-pick.md) that pass will poll and
fix. Neither result supersedes or substitutes for the other — a resumed run keeps both, one
recorded from `setup` and carried forward, one recomputed by `start` on every pass — and the
source assigns them no priority or preference between them.

Both are exercised by the same `workspace` pytest fixture: two real Git repositories plus the
`.code-workspace` manifest that names them, built once per test and read by both
`resolve_workspace_dirs` (behind `setup`) and `select_ci_repo` (behind `start`). Sharing that
fixture is a test-setup convenience, not a relationship between the two result formats
themselves — it grounds both format nodes in `workflows/tests/coder/fix_ci/test_flow.py` because
that is where their behavior is proved, not because one is preferred over the other.

- rule: `WorkspaceDirs` (from `setup`) and `CiRepoPick` (from `start`) are complementary results
  of the CI remediation flow's two setup steps, not competing implementations of one concept; no
  source-defined ranking exists between them.
- tests: `workflows/tests/coder/fix_ci/test_flow.py::workspace`
