---
type: concept
slug: ci-gating
title: Coder CI gating helpers
---
# Coder CI gating helpers

- code: `workflows/src/workhorse_workflows/coder/shared/ci.py` @277f211778fc
- tests: `workflows/tests/coder/fix_ci/test_flow.py`

This module supplies the repository selection, GitHub Actions polling and verified push operations used by the coder CI remediation flow. It treats an absent CI
surface as `unavailable`, but treats an API or permission failure as `blocked`, so the flow never
mistakes an unreadable gate for a passing one. All repository operations use the selected
repository directory rather than the process working directory.

## Methods

### select_ci_repo

- sig: `select_ci_repo(logger: logging.Logger, repo: str = "", processed: list[str] | None = None, workspace: str = "", launch_dir: str = "") -> CiRepoPick`
- does: resolves repositories from the workspace file and launch directory
- verify: count(subject="workspace repositories resolved for the CI loop", equals=1)
- does: selects the named repository when it is present and not already processed
- verify: json_path(path="$.repo", equals="api")
- does: selects the first unprocessed repository in workspace order when no name is supplied
- verify: count(subject="first unprocessed workspace repositories selected", equals=1)
- does: skips a named repository absent from the workspace with an empty pick and warning
- verify: count(subject="absent named repositories skipped", equals=1)
- does: returns an empty pick when every workspace repository is already processed
- verify: count(subject="empty picks for fully processed workspaces", equals=1)
- does: appends a selected repository to `processed` immediately
- verify: count(subject="selected repository processing list", equals=1)
- returns: a `CiRepoPick` containing the selected repository name, checkout path, and updated processed list
- verify: count(subject="repository picks returned", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::select_ci_repo` @277f211778fc
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_every_workspace_repo_is_checked_once_and_the_loop_ends`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_named_repo_pins_the_loop_to_that_one`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_repo_absent_from_the_workspace_is_a_warning_not_a_failure`
- emits: [ci-repo-pick](../formats/ci-repo-pick.md)

### poll_pr_checks

- sig: `poll_pr_checks(logger: logging.Logger, repo_dir: str, branch: str, pr_number: str = "", watch_timeout: int = 1200, poll_interval: int = 30) -> CiChecks`
- does: returns `unavailable` without contacting GitHub when no branch is supplied
- verify: count(subject="branchless CI polls", equals=1)
- does: returns `unavailable` when the repository has no configured GitHub token
- verify: count(subject="tokenless CI polls", equals=1)
- does: returns `unavailable` when the repository has no `origin` remote
- verify: count(subject="remoteless CI polls", equals=1)
- does: returns `unavailable` when the origin is not a GitHub repository
- verify: count(subject="non-GitHub CI polls", equals=1)
- does: returns `blocked` when a GitHub repository cannot be reached
- verify: count(subject="unreachable GitHub CI polls", equals=1)
- does: resolves an explicit numeric pull request number before resolving an open pull request by branch
- verify: count(subject="explicit pull request number resolutions", equals=1)
- does: evaluates Actions runs for the pull-request head commit rather than stale branch runs
- verify: count(subject="head commit Actions run evaluations", equals=1)
- does: treats non-completed runs as pending and waits before judging the verdict
- verify: count(subject="pending Actions run waits", equals=1)
- does: treats `failure`, `timed_out`, `cancelled`, `startup_failure`, `action_required`, and `stale` conclusions as failures
- verify: count(subject="failing Actions conclusions", equals=1)
- does: returns `passed` only when at least one Actions run exists and every run succeeds
- verify: json_path(path="$.status", equals="passed")
- does: returns `failed` with failing workflow names and run IDs when settled runs are red
- verify: json_path(path="$.summary", matches="/.+/")
- does: returns `unavailable` after six consecutive polls find no Actions runs
- verify: count(subject="runless CI polls after six attempts", equals=1)
- does: returns `blocked` when the pull-request head SHA cannot be read
- verify: count(subject="unreadable head SHA CI polls", equals=1)
- does: classifies authentication and permission errors as `blocked` without retrying them
- verify: count(subject="authentication errors classified as blocked", equals=1)
- does: retries other GitHub run-query errors until the watch timeout
- verify: count(subject="retried GitHub run-query errors", equals=1)
- does: returns `failed` when the watch timeout expires before runs settle
- verify: count(subject="watch timeouts reported as failed", equals=1)
- returns: a `CiChecks` status and summary describing the observed CI state
- verify: count(subject="CI check results returned", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::poll_pr_checks` @277f211778fc
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_no_branch_is_nothing_to_gate_on`
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_red_branch_is_fixed_pushed_and_re_polled_until_it_is_green`
- emits: [ci-checks](../formats/ci-checks.md)

### push_epic_branch

- sig: `push_epic_branch(logger: logging.Logger, root: Path, branch: str) -> Literal["pushed", "unavailable", "failed"]`
- does: returns `unavailable` without pushing when the branch is empty or does not exist locally
- does: returns `unavailable` when no GitHub token, origin remote, or GitHub origin repository is available
- does: attempts an HTTPS push for an existing branch when the repository has the required credentials and origin
- does: returns `failed` when the attempted push fails or the remote head does not advance
- does: returns `pushed` only after the remote head is verified equal to the local branch head
- returns: one of `pushed`, `unavailable`, or `failed` distinguishing whether the remote branch was verified
- verify: json_path(path="$", equals="pushed")
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::push_epic_branch` @277f211778fc

### push_ci_fix

- sig: `push_ci_fix(logger: logging.Logger, repo_dir: str, branch: str) -> PushOutcome`
- does: uses the supplied repository directory for the CI fix push
- does: falls back to the discovered repository root only when `repo_dir` is empty
- does: returns the push status and branch/root note in a `PushOutcome`
- returns: a `PushOutcome` with status `pushed`, `unavailable`, or `failed`
- code: `workflows/src/workhorse_workflows/coder/shared/ci.py::push_ci_fix` @277f211778fc
- emits: [push-outcome](../formats/push-outcome.md)
- verify: json_path(path="$.status", equals="failed")
