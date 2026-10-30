---
type: format
slug: code-change
title: Code change result
---
# Code change result

The code change result reports whether any product path moved since the code snapshot was taken.
A repository counts as moved when the set of its dirty product paths with their bytes differs from
the snapshot, or when a commit since the snapshot touched a product path, so a commit shows as a
change just as an edit does. The artifacts dir, the book and tool output are never product, so
changing only those reports no change. A run with no readable repository also reports a change,
because there is nothing left to watch.

- file: none — in-memory workflow result
- config: the code snapshot and the resolved code repositories
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::CodeChange` @0583ca2fc310
- detail: [Story worktree boundary](../concepts/story-worktree-boundary.md)

## Fields

### changed
- type: `bool`
- default: `true`
- required: false
- semantics: true when a product path differs from the snapshot or no repository could be read
- verify: json_path(path="$.changed", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::CodeChange.changed` @f3fa1285c426
