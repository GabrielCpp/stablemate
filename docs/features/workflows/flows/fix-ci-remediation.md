---
type: flow
slug: fix-ci-remediation
title: Coder CI remediation flow
---
# Coder CI remediation flow

- The `FixCi` sub-flow checks the epic branch in each selected workspace repository. A failed
  Actions verdict is handed to one fixer turn, then a verified push triggers another poll. The
  outer `poll -> start` transition advances to the next repository; the inner `push -> poll`
  transition rechecks the same repository. The [loop state](../ci-loop.md), [CI verdict](../ci-checks.md),
  [fixer result](../fix-ci-result.md), and [workspace directories](../workspace-dirs.md) are the
  data contracts carried by this flow.
- start: the flow has a `CiLoop` with the next workspace repository selected, or no repository remains
- verify: count(subject="selected CI remediation repositories", equals=1)
- start: the selected repository and branch are available before CI polling
- verify: count(subject="CI polls with selected repository and branch", equals=1)
- steps:
  - [setup](#setup)
  - [start](#start)
  - [poll](#poll)
  - [fix](#fix)
  - [push](#push)
- end: no workspace repository remains unprocessed and the flow returns an `unavailable` CI result
- verify: json_path(path="$.status", equals="unavailable")
- end: a passed poll returns a `passed` CI result without invoking the fixer
- verify: json_path(path="$.status", equals="passed")
- end: an unreadable CI poll raises `WorkflowFailed` instead of treating the repository as passed
- verify: exit_status(code=1)
- end: a red branch whose fix budget is exhausted returns a `failed` CI result with the last poll summary
- verify: json_path(path="$.status", equals="failed")
- end: a fixer refusal or unlanded push returns a `failed` CI result without another poll
- verify: count(subject="CI remediation terminal failures", equals=1)
- code: `workflows/src/workhorse_workflows/coder/fix_ci/flow.py::FixCi`
- detail: [coder main flow](coder-main.md)
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_every_workspace_repo_is_checked_once_and_the_loop_ends`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_red_branch_is_fixed_pushed_and_re_polled_until_it_is_green`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_the_fix_budget_is_spent_and_the_loop_reports_the_branch_still_red`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_fixer_that_says_it_cannot_stops_the_laps_instead_of_re_asking_it`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_push_that_does_not_land_ends_the_loop_instead_of_spending_an_attempt`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_the_attempt_budget_is_shared_across_repos_not_reset_per_repo`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_run_killed_in_the_fixer_resumes_on_that_turn_alone`

The workflow inputs are `repo` (empty means every workspace repository), `branch` (the full epic
branch name), `pr_number` (optional explicit pull request selector), `docs_path`, and
`workspace_file`; the latter two are empty when the run derives them from its repository context.
`MAX_ATTEMPTS` is three fix/push cycles for the whole run, not a per-repository reset.

## Steps

### setup

`setup` resolves the workspace and documentation directories once and returns a
[workspace directory set](../workspace-dirs.md). A resumed run carries that result rather than
re-deriving it.

### start

`start` calls `select_ci_repo` with the configured repository name and the loop's processed list.
An explicit repository is selected once; an empty name selects each workspace repository in order.
The selected repository is added to `processed` immediately, including when its later CI check
exhausts the budget. When no repository is selected, `start` finishes with the last CI verdict or
an `unavailable` result when no poll ran.

### poll

`poll` calls `poll_pr_checks` for the selected repository directory, branch, and optional PR number.
`blocked` raises `WorkflowFailed` because CI existed but could not be read. `unavailable` is
recorded in `unread` and follows the passed/advance path because there is no CI verdict to repair.
`passed` advances to `start`. A `failed` verdict is handed to `fix` while the lifetime attempt
budget remains; once it reaches three, the flow finishes with the last failed summary.

### fix

`fix` runs the `fix-ci` agent turn in the selected repository directory, adds the resolved docs and
workspace directories, and supplies the branch, the epic derived by removing `feat/`, and the
poll's failure summary. A `blocked` fixer result finishes as failed; `fixed` and `failed` both
continue to `push`, because only the subsequent poll decides whether CI is green.

### push

`push` calls `push_ci_fix` for the selected repository and branch. `pushed` and `unavailable`
continue to `poll` and increment the shared attempt count. Any other push status finishes as
failed without polling an unmoved pull-request head.
