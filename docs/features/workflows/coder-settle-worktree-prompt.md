---
type: format
slug: coder-settle-worktree-prompt
title: Coder settle-worktree prompt
---
# Coder settle-worktree prompt

- file: `workflows/src/workhorse_workflows/coder/main/prompts/settle-worktree.md`
- code: `workflows/src/workhorse_workflows/coder/main/flow.py::Coder.settle`
- detail: [coder main flow](flows/coder-main.md)
- detail: [story worktree boundary](concepts/story-worktree-boundary.md)
- detail: [coder prompt role resolution](concepts/coder-prompt-role-resolution.md)
- detail: [coder rendered schema contracts](concepts/coder-render-schema-contracts.md)

This envelope gives one chained turn the dirty paths left by a story and asks it to classify each
path, commit only work belonging to that story with the required trailers, and report unrelated
work as blocked. The workflow rechecks the tree after the turn; the prompt cannot itself authorize
a clean result.

## Fields

### story_path
- type: string path
- required: true
- semantics: story document used to identify which changes belong to the story
- verify: json_path(path="$.story_path", matches=".+")

### spec_dir
- type: string path
- required: true
- semantics: story plan and artifact directory used to classify dirty paths
- verify: json_path(path="$.spec_dir", matches=".+")

### epic
- type: string
- default: empty string
- required: false
- semantics: epic identity written into commits when the story belongs to a queued epic
- verify: json_path(path="$.epic", matches=".*")

### dirty_paths
- type: string
- required: true
- semantics: newline-separated package-relative paths still uncommitted after story completion
- verify: json_path(path="$.dirty_paths", matches=".*")

### story_slug
- type: string
- required: true
- semantics: story slug used to identify the work being settled
- verify: json_path(path="$.story_slug", matches=".+")

### story_id
- type: string
- required: true
- semantics: story identifier written into commits as the story trailer
- verify: json_path(path="$.story_id", matches=".+")

### result_schema
- type: string
- required: true
- semantics: rendered JSON contract for the `WorktreeSettled` reply
- verify: json_path(path="$.result_schema", matches=".+")
