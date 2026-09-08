---
type: flow
slug: fix-ci-remediation
title: Coder CI remediation flow
---
# Coder CI remediation flow

The `FixCi` sub-flow checks the configured epic branch in workspace repositories. It uses one
`CiLoop` value across all states. The [loop state](../ci-loop.md), [CI verdict](../ci-checks.md),
[fixer result](../fix-ci-result.md), and [workspace directories](../workspace-dirs.md) are the
data contracts carried by this flow. Its repository selection, polling, branch conversion, and
push behavior are defined by the [CI gating helpers](../concepts/ci-gating.md).

`repo` defaults to empty and selects every workspace repository in manifest order; a non-empty
value pins the run to that repository. `branch` defaults to empty and is the full branch ref,
normally `feat/<epic>`. `pr_number` defaults to empty and makes polling resolve the open PR by
branch; a supplied number selects that PR directly. `docs_path` and `workspace_file` default to
empty and are resolved from the repository context. `MAX_ATTEMPTS` is three fix/push cycles for
the complete run, shared across repositories.

- start: a `CiLoop` contains the next unprocessed workspace repository
- verify: count(subject="selected CI remediation repositories", equals=1)
- start: no workspace repository remains unprocessed
- verify: count(subject="processed CI remediation repositories", equals=2)
- start: a selected repository is available to the CI poll
- verify: count(subject="CI polls with selected repository and branch", equals=1)
- steps:
  - [setup](#setup)
  - [start](#start)
  - [poll](#poll)
  - [fix](#fix)
  - [push](#push)
- end: no workspace repository remains unprocessed and no CI poll has produced a verdict
- verify: json_path(path="$.status", equals="unavailable")
- end: an unavailable poll is recorded and the next repository is selected
- verify: count(subject="unread CI repositories", equals=2)
- end: a passed poll returns a `passed` CI result and does not invoke the fixer
- verify: json_path(path="$.status", equals="passed")
- end: an unreadable CI poll raises `WorkflowFailed`
- verify: exit_status(code=1)
- end: a red branch whose shared fix budget is exhausted returns a `failed` CI result
- verify: json_path(path="$.status", equals="failed")
- end: the terminal failed result carries the last poll or terminal failure summary
- verify: json_path(path="$.summary", matches="/.+/")
- end: a blocked fixer result returns a `failed` CI result without pushing
- verify: count(subject="CI remediation fixer terminal failures", equals=1)
- end: a push that is not pushed or unavailable returns a `failed` CI result without another poll
- verify: count(subject="CI remediation push terminal failures", equals=1)
- detail: [coder handoff boundary contract](../concepts/coder-handoff-boundary.md)
- detail: [coder fix-ci package](../concepts/coder-fix-ci-package.md)
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
`MAX_ATTEMPTS` is three fix/push cycles for the whole run, not a per-repository reset. The flow
uses one session key, `ci-fix:<branch>:<repo>`, per repository and resets that session whenever
the repository settles or the flow exits without another fixer turn.

The flow's terminal result is always a `Done` carrying the last `CiChecks` status, except when a poll
cannot read an existing CI surface and raises `WorkflowFailed`. A terminal reason replaces the last
poll summary, while each repository recorded in `unread` is appended to that summary. If no poll ran,
the status is `unavailable`.

The flow is implemented by `workflows/src/workhorse_workflows/coder/fix_ci/flow.py::FixCi`.

## Steps

### setup

- kind: prepare

`setup` resolves the workspace and documentation directories once and returns a
[workspace directory set](../workspace-dirs.md). The docs root is prepended when it is not already
one of the existing directories. It calls `resolve_workspace_dirs` through the workflow context,
and a resumed run carries that result rather than re-deriving it.

### start

- kind: drive

`start` calls `select_ci_repo` with the configured repository name and the loop's processed list.
An explicit repository is selected once; an empty name selects each workspace repository in order.
The selected repository is added to `processed` immediately, including when its later CI check
exhausts the budget. A named repository absent from the workspace is skipped with an empty pick.
When no repository is selected, `start` finishes with the last CI verdict or an `unavailable`
result when no poll ran. The selected repository name, checkout path, and updated processed list
are copied into the next `CiLoop` value before `poll` runs.

### poll

- kind: health

`poll` calls `poll_pr_checks` for the selected repository directory, branch, and optional PR number.
`blocked` raises `WorkflowFailed` because CI existed but could not be read. `unavailable` is
recorded in `unread` and follows the passed/advance path because there is no CI verdict to repair.
`passed` advances to `start`. A `failed` verdict is handed to `fix` while the lifetime attempt
budget is below three; once it reaches three, the flow finishes with the last failed summary. A
repository session is reset when `passed` or `unavailable` advances the outer loop, and when the
attempt budget ends.

### fix

- kind: drive

`fix` runs the `fix-ci` agent turn in the selected repository directory, adds the resolved docs and
workspace directories, and supplies the branch, the epic derived by removing `feat/`, and the
poll's failure summary. The turn uses medium power and the per-repository session key. A
`blocked` fixer result finishes as failed and resets that session. `fixed` and `failed` both
continue to `push`, because only the subsequent poll decides whether CI is green. The agent turn
is the only work in this state, so a checkpointed interruption resumes at `fix` with the same
repository, summary, and session rather than repeating the preceding poll.

The `fix-ci` prompt requires the agent to confirm the current branch without switching it, inspect
the reported Actions run and job logs through the Actions API, reproduce the failure with bounded
repository commands, repair only the CI cause, and rerun the same local gate. It forbids changes to
user-facing contracts when no story context is available. The agent commits on the epic branch
with an exact `Epic: <epic>` trailer and never pushes; the flow's `push` state owns that operation.
Its final response must be the declared [CI fixer result](../fix-ci-result.md) JSON object.

### push

- kind: run

`push` calls `push_ci_fix` for the selected repository and branch. `pushed` and `unavailable`
continue to `poll` and increment the shared attempt count. Any other push status finishes as
failed without polling an unmoved pull-request head, and resets the repository session.

The terminal helper reads the most recent `poll_pr_checks` output. If no poll ran, it uses
`unavailable`; otherwise it preserves that poll's status and replaces its summary with the
terminal reason. Any `unread` repository reasons are appended to the final summary so a completed
run distinguishes a passed repository from one whose CI was never gated.
