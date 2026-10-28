---
type: concept
slug: coder-main-pr-boundary
title: Coder main PR boundary
---
# Coder main PR boundary

The main Coder machine owns the pull-request boundary of a pr-mode run. Once the worklist is
empty, it opens one PR per repository the run branch changed and hands the branch to the ship
lane, which waits for CI and repairs it. The merge is left to a reviewer. A commit-mode run
never reaches this boundary. Remote operations are best-effort when a checkout has no usable
GitHub origin or credential: the run ends locally and leaves the branch for a manual PR.

Its result contract is the [run pull requests result](../formats/run-prs.md).

- code: `workflows/src/workhorse_workflows/coder/main/nodes/pr.py` @4f5e7daf9603

## Methods

### open_run_prs

- sig: `open_run_prs(logger, branch="", base_branch="main", epic="", story_path="", story_slug="", stories=None, repo_dir="", workspace="") -> RunPrs`
- does: returns a skipped result when no run branch is supplied
- verify: json_path(path="$.status", equals="skipped")
- does: skips a repository that lacks the run branch, whose run branch has nothing past its base, or that has no GitHub token
- verify: count(subject="PRs for repositories the run branch did not change", equals=0)
- does: pushes the run branch and opens one PR per remaining repository, targeting the run's base in the docs repository and each code repository's own base elsewhere, or reuses the PR already open for that branch
- verify: count(subject="PRs opened per changed repository", equals=1)
- does: titles each PR as a conventional `feat` subject scoped to the repository and described by the story's title, the epic's title, or the branch name
- verify: json_path(path="$.title", equals="feat(acme): epic One")
- does: lists the run's delivered stories in the PR body and leaves the merge to a reviewer
- verify: absent(subject="PR merge operation by the run")
- returns: `opened` with every PR URL when at least one PR exists, otherwise `skipped`
- verify: json_path(path="$.status", equals="opened")
- code: `workflows/src/workhorse_workflows/coder/main/nodes/pr.py::open_run_prs` @4f5e7daf9603
- tests: `workflows/tests/coder/test_workflow.py::test_a_pr_run_lands_every_item_on_one_branch_and_opens_no_pr_offline`
- tests: `workflows/tests/coder/test_workflow.py::test_an_opened_pr_goes_to_the_ship_lane_for_ci_and_stays_open`
