---
type: format
slug: worktree-snapshot
title: Worktree snapshot
---
# Worktree snapshot

The pre-plan snapshot records `git status --porcelain` output for each existing code repository,
excluding the docs root where planning artifacts are intentionally written. A repository whose
status cannot be read is omitted so the later scrub does not guess at its state.

- file: none — in-memory workflow result
- config: workspace repository paths and the resolved docs root
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::WorktreeSnapshot`
- detail: [Coder story pipeline](concepts/story-pipeline.md)
- tests: `workflows/tests/coder/shared/test_clean_tree.py::test_the_snapshot_covers_the_code_repos_and_not_the_docs_root`

## Fields

### status
- type: `dict[str, str]`
- default: empty mapping
- required: false
- semantics: `git status --porcelain` output is keyed by absolute code-repository path
- verify: json_path(path="$.status", matches=".*")
- semantics: unreadable or non-directory repositories are absent
- verify: absent(subject="unreadable or non-directory repositories")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::WorktreeSnapshot.status`
