---
type: format
slug: worktree-snapshot
title: Worktree snapshot
---
# Worktree snapshot

The code snapshot records `HEAD` followed by the dirty product paths, each with the sha256 of its bytes,
for every existing workspace repository, the docs root included. The artifacts dir, the book and tool
output are never product, so they are left out of the record. A repository whose `HEAD` or dirty paths
cannot be read is omitted so the later comparison does not guess at its state.

- file: none — in-memory workflow result
- config: workspace repository paths and the resolved docs root
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::PorcelainSnapshot` @47f1b92122df
- detail: [Story worktree boundary](../concepts/story-worktree-boundary.md)

## Fields

### status
- type: `dict[str, str]`
- default: empty mapping
- required: false
- semantics: `HEAD` followed by one `<path>\0<sha256>` line per dirty product path is keyed by absolute repository path
- verify: json_path(path="$.status", matches="^\{.*\}$")
- semantics: unreadable or non-directory repositories are absent
- verify: absent(subject="unreadable or non-directory repositories")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::PorcelainSnapshot.status` @f3fa1285c426
