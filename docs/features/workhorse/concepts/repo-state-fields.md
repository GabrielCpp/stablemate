---
type: concept
slug: repo-state-fields
title: RepoState fields
---
# RepoState fields

`RepoState` is one point-in-time repository observation, not a choice among alternative
representations. Its fields are complementary facts: `path` identifies what was sampled,
`root` and `origin` identify the repository, `head` and `branch` identify its revision, and
`dirty` and `stash` describe requested working-tree observations. The source deliberately
uses empty strings and `None` for unavailable facts, rather than inventing clean or
repository-less values.

No field ranks above or replaces another. Read the field that answers the diagnostic question,
and retain the complete record when its sampled repository and revision context matter.

- code: `workhorse/workhorse/gitstate.py::RepoState`
- rule: select the field that answers the required repository fact; the fields are complementary and none supersedes another
- detail: [RepoState concept selection](repo-state-concept-selection.md)
