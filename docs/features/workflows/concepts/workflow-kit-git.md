---
type: concept
slug: workflow-kit-git
title: Workflow kit Git
---
# Workflow kit Git

The Git kit separates a commit scoped to explicit paths from a deliberate whole-tree commit.
`commit_paths` makes no commit for an empty or unchanged scope and never widens that scope;
`commit_all` is reserved for a checkout the run owns. Both report a non-repository path as no
commit, but surface a Git refusal rather than misreporting it as a clean tree.

- code: `workflows/src/workhorse_workflows/kit/git.py::commit_paths`
- code: `workflows/src/workhorse_workflows/kit/git.py::commit_all`
- tests: `workflows/tests/test_kit_git.py::test_commit_paths_stages_only_the_named_paths`
- tests: `workflows/tests/test_kit_git.py::test_commit_paths_with_no_pathspecs_commits_nothing`
- tests: `workflows/tests/test_kit_git.py::test_commit_all_still_sweeps_the_whole_tree`
- tests: `workflows/tests/test_kit_git.py::test_a_refused_commit_raises_instead_of_reading_as_an_empty_one`
