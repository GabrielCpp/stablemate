---
type: format
slug: code-change
title: Code change result
---
# Code change result

The code change result reports whether any code repository moved since the code snapshot was
taken. A repository counts as moved when its `HEAD` or its `git status --porcelain` output differs
from the snapshot, so a commit shows as a change just as an edit does. A run with no readable code
repository also reports a change, because there is nothing left to watch.

- file: none — in-memory workflow result
- config: the code snapshot and the resolved code repositories
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::CodeChange` @67086ecf5f6c
- detail: [Story worktree boundary](../concepts/story-worktree-boundary.md)

## Fields

### changed
- type: `bool`
- default: `true`
- required: false
- semantics: true when the code repositories differ from the snapshot or none could be read
- verify: json_path(path="$.changed", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::CodeChange.changed` @67086ecf5f6c
