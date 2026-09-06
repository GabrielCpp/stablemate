---
type: concept
slug: ci-gating
title: Coder CI gating helpers
---
# Coder CI gating helpers

- code: `workflows/src/workhorse_workflows/coder/shared/ci.py`
- tests: `workflows/tests/coder/fix_ci/test_flow.py`

This module supplies the repository selection, GitHub Actions polling, branch-name conversion,
and verified push operations used by the coder CI remediation flow. It treats an absent CI
surface as `unavailable`, but treats an API or permission failure as `blocked`, so the flow never
mistakes an unreadable gate for a passing one. All repository operations use the selected
repository directory rather than the process working directory.

## Methods

### epic_branch

- sig: `epic_branch(epic: str) -> str`
- does: prefixes a non-empty epic identifier with `feat/`
- does: returns an empty string when the epic identifier is empty
- returns: the full branch ref used for an epic pull request
- verify: json_path(path="$", equals="feat/EPIC-1")
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::epic_branch`

### branch_epic

- sig: `branch_epic(branch: str) -> str`
- does: removes the `feat/` prefix when the branch carries that prefix
- does: leaves branches without the `feat/` prefix unchanged
- returns: the bare epic identifier represented by the branch ref
- verify: json_path(path="$", equals="EPIC-1")
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::branch_epic`

### select_ci_repo

- sig: `select_ci_repo(logger: logging.Logger, repo: str = "", processed: list[str] | None = None, workspace_file: str = "", launch_dir: str = "") -> CiRepoPick`
- does: resolves repositories from the workspace file and launch directory
- does: selects the named repository when it is present and not already processed
- does: selects the first unprocessed repository in workspace order when no name is supplied
- does: skips a named repository absent from the workspace with an empty pick and warning
- does: returns an empty pick when every workspace repository is already processed
- does: appends a selected repository to `processed` immediately
- returns: a `CiRepoPick` containing the selected repository name, checkout path, and updated processed list
- verify: json_path(path="$.repo", equals="api")
- verify: count(subject="selected repository processing list", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::select_ci_repo`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_every_workspace_repo_is_checked_once_and_the_loop_ends`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_named_repo_pins_the_loop_to_that_one`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_repo_absent_from_the_workspace_is_a_warning_not_a_failure`

### poll_pr_checks

- sig: `poll_pr_checks(logger: logging.Logger, repo_dir: str, branch: str, pr_number: str = "", watch_timeout: int = 1200, poll_interval: int = 30) -> CiChecks`
- does: returns `unavailable` without contacting GitHub when no branch is supplied
- does: returns `unavailable` when the repository has no configured GitHub token
- does: returns `unavailable` when the repository has no `origin` remote
- does: returns `unavailable` when the origin is not a GitHub repository
- does: returns `blocked` when a GitHub repository cannot be reached
- does: resolves an explicit numeric pull request number before resolving an open pull request by branch
- does: evaluates Actions runs for the pull-request head commit rather than stale branch runs
- does: treats non-completed runs as pending and waits before judging the verdict
- does: treats `failure`, `timed_out`, `cancelled`, `startup_failure`, `action_required`, and `stale` conclusions as failures
- does: returns `passed` only when at least one Actions run exists and every run succeeds
- does: returns `failed` with failing workflow names and run IDs when settled runs are red
- does: returns `unavailable` after six consecutive polls find no Actions runs
- does: returns `blocked` when the pull-request head SHA cannot be read
- does: classifies authentication and permission errors as `blocked` without retrying them
- does: retries other GitHub run-query errors until the watch timeout
- does: returns `failed` when the watch timeout expires before runs settle
- returns: a `CiChecks` status and summary describing the observed CI state
- verify: json_path(path="$.status", equals="passed")
- verify: json_path(path="$.summary", matches="/.+/")
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::poll_pr_checks`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_no_branch_is_nothing_to_gate_on`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_red_branch_is_fixed_pushed_and_re_polled_until_it_is_green`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_the_fix_budget_is_spent_and_the_loop_reports_the_branch_still_red`

### push_epic_branch

- sig: `push_epic_branch(logger: logging.Logger, root: Path, branch: str) -> Literal["pushed", "unavailable", "failed"]`
- does: returns `unavailable` without pushing when the branch is empty or does not exist locally
- does: returns `unavailable` when no GitHub token, origin remote, or GitHub origin repository is available
- does: attempts an HTTPS push for an existing branch when the repository has the required credentials and origin
- does: returns `failed` when the attempted push fails or the remote head does not advance
- does: returns `pushed` only after the remote head is verified equal to the local branch head
- returns: one of `pushed`, `unavailable`, or `failed` distinguishing whether the remote branch was verified
- verify: json_path(path="$", equals="pushed")
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::push_epic_branch`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_push_that_does_not_land_ends_the_loop_instead_of_spending_an_attempt`

### push_ci_fix

- sig: `push_ci_fix(logger: logging.Logger, repo_dir: str, branch: str) -> PushOutcome`
- does: uses the supplied repository directory for the CI fix push
- does: falls back to the discovered repository root only when `repo_dir` is empty
- does: returns the push status and branch/root note in a `PushOutcome`
- returns: a `PushOutcome` with status `pushed`, `unavailable`, or `failed`
- verify: json_path(path="$.status", equals="failed")
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::push_ci_fix`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_push_that_does_not_land_ends_the_loop_instead_of_spending_an_attempt`
