---
type: flow
slug: fix-ci-remediation
title: Coder CI remediation flow
---
# Coder CI remediation flow

The `FixCi` sub-flow is the ship lane's owner for CI. It checks the configured epic branch in
workspace repositories, runs one owner turn per red check, and, when it is given a `base`, merges
the epic's pull request once every repository has been read. It uses one `CiLoop` value across
its states. The [loop state](../formats/ci-loop.md), [CI verdict](../formats/ci-checks.md),
[fixer result](../formats/fix-ci-result.md), and [workspace directories](../formats/workspace-dirs.md) are the
data contracts carried by this flow. Its repository selection, polling, branch conversion, and
push behavior are defined by the [CI gating helpers](../concepts/ci-gating.md).

`repo` defaults to empty and selects every workspace repository in manifest order; a non-empty
value pins the run to that repository. `branch` defaults to empty and is the full branch ref,
normally `feat/<epic>`. `pr_number` defaults to empty and makes polling resolve the open PR by
branch; a supplied number selects that PR directly. `workspace` defaults to
empty and resolves from the repository context. `base` defaults to empty and turns the merge
lane on when set. `operator_mode` defaults to `auto`. Each repository gets its own budget of
`MAX_LAPS` repair turns, and the epic's merge gets the same cap.

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-coder.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-coder.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [coder handoff boundary contract](../concepts/coder-handoff-boundary.md)
- detail: [coder fix-ci package](../concepts/coder-fix-ci-package.md)
- detail: [coder main flow](coder-main.md)
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_every_workspace_repo_is_checked_once_and_the_loop_ends`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_red_branch_is_fixed_pushed_and_re_polled_until_it_is_green`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_blocked_owner_in_human_mode_parks_and_resumes_with_the_answer`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_push_that_does_not_land_parks_instead_of_spending_a_lap`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_each_repo_gets_its_own_lap_budget`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_run_killed_in_the_owner_turn_resumes_on_that_turn_alone`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_the_ship_lane_merges_once_every_repo_is_read`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_refused_merge_gets_a_merge_turn_and_ci_is_read_again_before_the_retry`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_merge_turn_that_cannot_decide_parks_instead_of_spending_the_budget`

The flow keeps one owner session per repository, keyed `ci-fix:<branch>:<repo>`, and one merge
session keyed `merge-fix:<epic>`. A session is reset when its repository settles. A CI fix has no
story folder, so its operator gate lives under the launch repository's operator directory at
`ci-fix/<epic>/gate.md`.

The flow's terminal result is a `Done` carrying the last `CiChecks` status. A terminal reason
replaces the last poll summary, and each repository recorded in `unread` is appended to that
summary. If no poll ran, the status is `unavailable`.

The flow is implemented by `workflows/src/workhorse_workflows/coder/fix_ci/flow.py::FixCi`.

The stages, in order: [setup](#setup), [start](#start), [poll](#poll), [work](#work), [check](#check), [merge](#merge), [fix-merge](#fix-merge), [operator-block](#operator-block).

The flow starts when a `CiLoop` contains the next unprocessed workspace repository; or when no workspace repository remains unprocessed; or when a selected repository is available to the CI poll.
It ends in one of these ways: no workspace repository remains unprocessed, no `base` is set, and no CI poll has produced a verdict; an unavailable poll is recorded and the next repository is selected; a passed poll advances to the next repository and does not invoke the owner; an unreadable CI poll parks on the operator instead of failing the run; a red branch whose repair laps are spent parks on the operator; a blocked owner result parks on the operator; a push that is not pushed or unavailable parks on the operator without another poll; a merge that lands, or a merge with nothing to merge, finishes the run; a merge still refused after its attempt cap parks on the operator and flags the pull request.

## Steps

### setup

- kind: prepare

`setup` resolves the workspace and documentation directories once and returns a
[workspace directory set](../formats/workspace-dirs.md). The docs root is prepended when it is not already
one of the existing directories. It calls `resolve_workspace_dirs` through the workflow context,
and a resumed run carries that result rather than re-deriving it.

### start

- kind: drive

`start` calls `select_ci_repo` with the configured repository name and the loop's processed list.
An explicit repository is selected once; an empty name selects each workspace repository in order.
The selected repository is added to `processed` immediately, and its lap count starts at zero. A
named repository absent from the workspace is skipped with an empty pick. When no repository is
left, `start` hands a run with a `base` to `merge` and finishes any other run with the last CI
verdict, or an `unavailable` result when no poll ran.

### poll

- kind: health

`poll` calls `poll_pr_checks` for the selected repository directory, branch, and optional PR number
and routes the verdict. `blocked` takes the block path because CI existed but could not be read.
`unavailable` is recorded in `unread` and advances to `start`, because there is no CI verdict to
repair. `passed` advances to `start`. A `failed` verdict starts an owner turn while the repository's
laps are below `MAX_LAPS`; once they reach it, the checks go to the block path. A repository session
is reset when `passed` or `unavailable` advances the outer loop.

### work

- kind: drive

`work` runs the `fix-ci` owner turn in the selected repository directory under the repository's
session, adds the resolved docs and workspace directories, and supplies the branch, the epic
derived from it, the failing checks' summary as the report, and the operator's last answer. The
turn runs at high power under the shared owner profile with no wall-clock bound and a silence
limit. A `blocked` result goes to the block path. Any other result continues to `check`. The agent
turn is the only work in this state, so a checkpointed interruption resumes at `work` with the same
repository, report, and session rather than repeating the preceding poll.

The `fix-ci` prompt requires the agent to confirm the current branch without switching it, inspect
the reported Actions run and job logs through the Actions API, reproduce the failure with bounded
repository commands, repair only the CI cause, and rerun the same local gate. It forbids changes to
user-facing contracts when no story context is available. The agent commits on the epic branch
with an exact `Epic: <epic>` trailer and never pushes; the flow's `check` state owns that operation.
Its final response must be the declared [CI fixer result](../formats/fix-ci-result.md) JSON object.

### check

- kind: run

`check` calls `push_ci_fix` for the selected repository and branch. `pushed` and `unavailable`
continue: the flow polls CI again and routes the new verdict with the lap count raised by one. Any
other push status takes the block path without polling an unmoved pull-request head.

### merge

- kind: run

`merge` runs only for a run with a `base`, after every repository has been read. It calls
`merge_pr` for the epic. A `merged` or `unavailable` outcome resets the merge session and finishes
the run. A refused merge below `MAX_LAPS` attempts goes to `fix-merge`. At the cap, the flow takes
the block path with a note that the epic still does not merge into the base.

### fix-merge

- kind: drive

`fix-merge` runs the `fix-merge` owner turn under the merge session with the epic, branch, base,
and the operator's last answer. A `blocked` result takes the block path. Otherwise the flow pushes
the resolution and returns to `start` with a fresh loop whose merge count is one higher, so CI is
read again before the next merge attempt. A push that does not land takes the block path.

### operator-block

- kind: drive

A block takes the `resolve` turn in `auto` mode, which runs the shared operator-resolution prompt
and, when it answers, resumes through `read_operator`. In a human operator mode, or once
`MAX_BLOCKS` blocks have been spent, the flow writes the block to the CI gate document and returns
`Await`. When the block came from a merge, it also flags the pull request through
`flag_merge_failure`. `read_operator` reads the answer back and resumes `merge` with a zero merge
count, or `work` with a zero lap count and the block's notes as the report.
