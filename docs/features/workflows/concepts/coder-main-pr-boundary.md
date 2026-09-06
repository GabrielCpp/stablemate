---
type: concept
slug: coder-main-pr-boundary
title: Coder main PR boundary
---
# Coder main PR boundary

The main Coder machine owns the pull-request boundary for both execution modes. Epic mode
prunes its completed queue, opens one epic PR when the branch is independently shippable, polls
and repairs CI, and merges or parks for an operator. Story mode opens one review-only PR per
affected code repository and never auto-merges it. Remote operations are best-effort when the
checkout has no usable GitHub origin or credential: the workflow advances locally and leaves the
branch for manual follow-up.

Its result contracts are [pull request gate](../pr-gate.md), [merge outcome](../merge-outcome.md),
[story pull request](../story-pr.md), [CI failure flag](../ci-flagged.md), [merge failure flag](../merge-flagged.md),
and [merge fix](../merge-fix-result.md).

- code: `workflows/src/workhorse_workflows/coder/main/nodes/pr.py`

## Methods

### open_pr

- sig: `open_pr(logger, epic="", base_branch="main", run_dir="", repo_dir="") -> PrGate`
- does: returns a non-gating result when no epic is supplied
- verify: count(subject="non-gating PR gate records", equals=1)
- does: commits the completed epic's queue-prune change before attempting remote PR work
- verify: count(subject="completed epic queue-prune commits", equals=1)
- does: declines to open a PR when the branch contains unmerged work from an epic set aside in the same run
- verify: absent(subject="PR for a branch carrying set-aside work")
- does: attempts to push and open one epic PR when the branch is independently shippable
- verify: count(subject="epic PR gate records", equals=1)
- returns: a `PrGate` identifying the epic and base branch when remote gating is required, otherwise a non-gating result
- verify: count(subject="epic PR result records", equals=1)
- code: `workflows/src/workhorse_workflows/coder/main/nodes/pr.py::open_pr`
- tests: `workflows/tests/coder/test_workflow.py::test_the_pr_cluster_passes_through_offline_and_still_advances_the_queue`
- tests: `workflows/tests/coder/test_workflow.py::test_an_epic_branch_carrying_a_set_aside_epic_declines_to_open_a_pr`

### merge_pr

- sig: `merge_pr(logger, epic="", base_branch="main", repo_dir="") -> MergeOutcome`
- does: reports unavailable without an epic, usable credential, GitHub origin, or reachable repository
- verify: count(subject="unavailable merge outcome records", equals=1)
- does: treats an already merged pull request on resume as merged and synchronizes the local base branch
- verify: count(subject="resumed merged pull-request outcomes", equals=1)
- does: selects the first merge method allowed by the repository and attempts to merge the epic branch
- verify: count(subject="merge method selections", equals=1)
- returns: `merged`, `failed`, or `unavailable` with the base branch recorded
- verify: count(subject="merge outcome records", equals=1)
- code: `workflows/src/workhorse_workflows/coder/main/nodes/pr.py::merge_pr`
- tests: `workflows/tests/coder/test_workflow.py::test_a_merged_epic_branch_is_reused_rather_than_refused`
- tests: `workflows/tests/coder/test_workflow.py::test_a_squash_merged_branch_counts_as_merged`

### flag_ci_failure

- sig: `flag_ci_failure(logger, epic="", attempts="?", summary="", repo_dir="") -> CiFlagged`
- does: records the red CI summary and attempt count in an operator-facing warning
- verify: count(subject="CI failure operator warnings", equals=1)
- does: comments on the epic PR when a reachable open PR exists, without making comment failure fatal
- verify: count(subject="CI failure PR comment attempts", equals=1)
- returns: whether the CI failure note was posted to the PR
- verify: count(subject="CI failure flag records", equals=1)
- code: `workflows/src/workhorse_workflows/coder/main/nodes/pr.py::flag_ci_failure`

### flag_merge_failure

- sig: `flag_merge_failure(logger, epic="", base_branch="main", attempts="?", repo_dir="") -> MergeFlagged`
- does: records that merge attempts were exhausted and identifies the epic branch and base branch for operator review
- verify: count(subject="merge failure operator warnings", equals=1)
- does: comments on the epic PR when a reachable open PR exists, without making comment failure fatal
- verify: count(subject="merge failure PR comment attempts", equals=1)
- returns: whether the merge failure note was posted to the PR
- verify: count(subject="merge failure flag records", equals=1)
- code: `workflows/src/workhorse_workflows/coder/main/nodes/pr.py::flag_merge_failure`

### open_story_pr

- sig: `open_story_pr(logger, story_slug="", base_branch="main", story_path="", spec_dir="", story_branch="", repo_dir="", workspace_file="") -> StoryPr`
- does: returns an empty result when no story or affected code repository is available
- verify: count(subject="empty story PR result records", equals=1)
- does: creates or reuses one review-only PR for each affected code repository, committing pending story work on its story branch first
- verify: count(subject="affected repository story PR results", equals=1)
- does: builds each PR from the story description, plan summary, and at most six QA screenshots
- verify: count(subject="story PR bodies", equals=1)
- does: excludes the documentation repository and never auto-merges the story PRs
- verify: absent(subject="story PR merge operations")
- returns: `opened`, `exists`, or `skipped` aggregate status with URLs for opened or existing PRs
- verify: count(subject="story PR result records", equals=1)
- code: `workflows/src/workhorse_workflows/coder/main/nodes/pr.py::open_story_pr`
- tests: `workflows/tests/coder/test_workflow.py::test_story_mode_cuts_its_own_branch_and_ends_at_its_own_pr`
