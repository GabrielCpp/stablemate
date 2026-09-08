---
type: concept
slug: coder-review-input-selection
title: Coder review input selection
---
# Coder review input selection

`Review.start` supplies these four arguments in one code-review turn. They are complementary
inputs, not alternative ways to identify one review target: the story path gives the planned
scope, repository paths give the local changes to inspect, a branch narrows the review only when
the run is branch-scoped, and a pull request supplies optional state and a destination for
findings. The source passes each value under its own argument name and does not define a
substitute, deprecation, or priority among them.

- rule: Supply `story_path` and `affected_repo_paths` for every review; add `branch` only for a
  branch-scoped review and `pr_number` only when a pull request's state or inline comments are
  relevant. No field supersedes another or has a source-defined ranking.

## Methods

### Review.start

- sig: `start() -> Continue | Done`
- does: resolve story paths and dispatch a code review turn
- verify: created(subject="CodeReviewResult")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.start`
- tests: `workflows/tests/coder/review/test_flow.py`

### require_story_file

- sig: `require_story_file(ctx: StoryPaths) -> None`
- does: validate that the story file exists as a real file on disk
- verify: json_path(path="exception", absent=True)
- raises: `WorkflowFailed` when story slug does not resolve to an existing story file
- verify: json_path(path="exception.type", equals="WorkflowFailed")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::require_story_file`
