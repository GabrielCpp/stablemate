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

- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.start`
- rule: Supply `story_path` and `affected_repo_paths` for every review; add `branch` only for a
  branch-scoped review and `pr_number` only when a pull request's state or inline comments are
  relevant. No field supersedes another or has a source-defined ranking.
