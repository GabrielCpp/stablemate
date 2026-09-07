---
type: format
slug: coder-queue-worktree-cleanliness
title: Coder queue worktree cleanliness
---
# Coder queue worktree cleanliness

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::WorktreeCleanliness`
- detail: [coder shared library](concepts/coder-shared-library.md)

The cleanliness result reports whether story-owned implementation paths remain uncommitted after
the development gate. Paths that were dirty before the story and untouched by it are excluded.

## Fields

### clean
- type: boolean
- default: `false`
- required: false
- semantics: whether no story-owned uncommitted paths remain
- verify: json_path(path="$.clean", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::WorktreeCleanliness`
- detail: [coder queue worktree cleanliness field roles](concepts/coder-queue-worktree-cleanliness-field-roles.md)

### dirty
- type: list of strings
- default: `[]`
- required: false
- semantics: repository-qualified paths still uncommitted after exclusions
- verify: count(subject="dirty paths", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::WorktreeCleanliness`
- detail: [coder queue worktree cleanliness field roles](concepts/coder-queue-worktree-cleanliness-field-roles.md)

### repos
- type: list of strings
- default: `[]`
- required: false
- semantics: repository names inspected for the story
- verify: count(subject="inspected repositories", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::WorktreeCleanliness`
- detail: [coder queue worktree cleanliness field roles](concepts/coder-queue-worktree-cleanliness-field-roles.md)
