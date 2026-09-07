---
type: concept
slug: story-worktree-boundary
title: Story worktree boundary
---
# Story worktree boundary

The coder records repository paths that were already dirty before a story's first development
turn, then charges the story only for paths whose bytes changed after that boundary. This keeps
abandoned work from a previous story out of the current story's documentation and QA obligations.
The boundary is conservative: unreadable, deleted, malformed, or changed paths are not excused.

- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::__all__`
- detail: [Coder story pipeline](story-pipeline.md)

## Methods

### digest
- sig: `digest(root: Path, rel: str) -> str`
- does: computes the SHA-256 digest of the bytes at `root / rel`
- verify: json_path(path="$.digest", matches="^[0-9a-f]{64}$")
- returns: the empty string when the path cannot be read as a file
- verify: json_path(path="$.digest", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::digest`

### untouched_since
- sig: `untouched_since(root: Path, snapshot: tuple[str, ...]) -> set[str]`
- does: parses snapshot entries as a relative path, NUL separator, and recorded digest
- verify: count(subject="valid snapshot entries considered", equals=1)
- does: ignores entries without all three required parts
- verify: count(subject="malformed snapshot entries included", equals=0)
- does: includes a path only when its current digest equals the recorded digest
- verify: count(subject="byte-identical pre-existing paths retained", equals=1)
- does: excludes paths that were edited, deleted, unreadable, or directories
- verify: count(subject="changed or unreadable paths excused", equals=0)
- returns: the set of relative paths that remain byte-identical
- verify: json_path(path="$.untouched", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::untouched_since`

### snapshot_worktree_state
- sig: `snapshot_worktree_state(logger: logging.Logger, docs_path: str = "", repo_dir: str = "") -> WorktreeSnapshot`
- does: resolves the repository root from the documentation and repository path inputs
- verify: json_path(path="$.root", matches=".+")
- does: records modified tracked paths and untracked paths reported by the repository
- verify: count(subject="pre-existing dirty paths recorded", equals=2)
- does: stores each readable path as its repository-relative name, a NUL separator, and its SHA-256 digest
- verify: json_path(path="$.entries", matches=".*")
- does: sorts and de-duplicates the recorded path entries
- verify: count(subject="duplicate snapshot entries", equals=0)
- does: returns an empty entry list when repository state cannot be read
- verify: count(subject="snapshot entries after repository state read failure", equals=0)
- returns: a `WorktreeSnapshot` containing entries and a human-readable note
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::snapshot_worktree_state`
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_snapshot_records_what_was_already_dirty_with_its_bytes`

## Fields

### entries
- type: `list[str]`
- default: empty list
- required: false
- semantics: each item is `<repo-relative path>\0<sha256 of file bytes>` for a path dirty before the story started
- verify: json_path(path="$.entries", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::WorktreeSnapshot.entries`

### notes
- type: `str`
- default: empty string
- required: false
- semantics: explains the number of recorded paths or why repository state was unavailable
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::WorktreeSnapshot.notes`
