---
type: format
slug: worktree-snapshot
title: Worktree snapshot
---
# Worktree snapshot

The code snapshot records `HEAD` followed by `git status --porcelain` output for each existing code
repository, excluding the docs root where planning artifacts are intentionally written. A repository
whose `HEAD` or status cannot be read is omitted so the later comparison does not guess at its state.

- file: none — in-memory workflow result
- config: workspace repository paths and the resolved docs root
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::PorcelainSnapshot` @67086ecf5f6c
- detail: [Story worktree boundary](../concepts/story-worktree-boundary.md)

## Fields

### status
- type: `dict[str, str]`
- default: empty mapping
- required: false
- semantics: `HEAD` followed by `git status --porcelain` output is keyed by absolute code-repository path
- verify: json_path(path="$.status", matches="^\{.*\}$")
- semantics: unreadable or non-directory repositories are absent
- verify: absent(subject="unreadable or non-directory repositories")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::PorcelainSnapshot.status` @67086ecf5f6c
