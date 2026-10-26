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

- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::__all__` @7a230e488348
- detail: [Coder story pipeline](story-pipeline.md)

## Methods

### digest
- sig: `digest(root: Path, rel: str) -> str`
- does: computes the SHA-256 digest of the bytes at `root / rel`
- verify: json_path(path="$.digest", matches="^[0-9a-f]{64}$")
- returns: the empty string when the path cannot be read as a file
- verify: json_path(path="$.digest", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::digest` @7a230e488348

### untouched_since
- sig: `untouched_since(root: Path, snapshot: tuple[str, ...]) -> set[str]`
- does: parses snapshot entries as a relative path, NUL separator, recorded digest, and an optional NUL-separated owner checkout path
- verify: count(subject="valid snapshot entries considered", equals=1)
- does: ignores entries missing a path or a recorded digest, or whose owner is neither empty nor this root's own resolved path
- verify: count(subject="malformed snapshot entries included", equals=0)
- does: includes a path only when its current digest equals the recorded digest
- verify: count(subject="byte-identical pre-existing paths retained", equals=1)
- does: excludes paths that were edited, deleted, unreadable, or directories
- verify: count(subject="changed or unreadable paths excused", equals=0)
- returns: the set of relative paths that remain byte-identical
- verify: json_path(path="$.untouched", equals="example untouched")
- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::untouched_since` @7a230e488348

### snapshot_worktree_state
- sig: `snapshot_worktree_state(logger: logging.Logger, repo_dir: str = "", roots: list[str] | None = None) -> DirtyAtStart`
- does: resolves the single repository root from the documentation and repository path inputs when `roots` is not given
- verify: json_path(path="$.root", equals="docs/stories")
- does: snapshots every checkout in `roots` instead when it is given, tagging each entry with that checkout's resolved path as its owner
- verify: count(subject="multi-root worktree snapshots", equals=1)
- does: records modified tracked paths and untracked paths reported by the repository
- verify: count(subject="pre-existing dirty paths recorded", equals=2)
- does: stores each readable path as its repository-relative name, a NUL separator, its SHA-256 digest, and the owner suffix when one applies
- verify: json_path(path="$.entries", equals="example entries")
- does: sorts and de-duplicates the recorded path entries
- verify: count(subject="duplicate snapshot entries", equals=0)
- does: returns an empty entry list when repository state cannot be read and `roots` is not given
- verify: count(subject="snapshot entries after repository state read failure", equals=0)
- does: skips and logs a checkout whose state cannot be read without failing the rest, when `roots` is given
- verify: count(subject="skipped unreadable root checkouts", equals=0)
- returns: a `DirtyAtStart` containing entries and a human-readable note
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::snapshot_worktree_state` @7a230e488348
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_snapshot_records_what_was_already_dirty_with_its_bytes`

### snapshot_code_state
- sig: `snapshot_code_state(logger: logging.Logger, repo_dir: str = "", workspace: str = "") -> PorcelainSnapshot`
- does: reads `HEAD` and `git status --porcelain` for every workspace repository that is a directory other than the docs root
- verify: count(subject="code repositories snapshotted", equals=1)
- does: omits a repository whose `HEAD` or status cannot be read
- verify: absent(subject="unreadable repositories in the code snapshot")
- returns: a `PorcelainSnapshot` keyed by absolute repository path
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::snapshot_code_state` @7a230e488348
- detail: [Worktree snapshot](../formats/worktree-snapshot.md)

### code_changed
- sig: `code_changed(logger: logging.Logger, before: dict[str, str] | None = None, repo_dir: str = "", workspace: str = "") -> CodeChange`
- does: reads the current state of the code repositories the same way the snapshot did
- verify: count(subject="code repositories re-read", equals=1)
- does: reports a change when the current state differs from `before`, including a new commit
- verify: json_path(path="$.changed", equals=true)
- does: reports a change when no code repository can be read
- returns: a `CodeChange`
- verify: count(subject="code change results", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/worktree.py::code_changed` @7a230e488348
- detail: [Code change result](../formats/code-change.md)

## Fields

### entries
- type: `list[str]`
- default: empty list
- required: false
- semantics: each item is `<repo-relative path>\0<sha256 of file bytes>` for a path dirty before the story started
- verify: json_path(path="$.entries", matches="^\[.*\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::DirtyAtStart.entries` @67086ecf5f6c

### notes
- type: `str`
- default: empty string
- required: false
- semantics: explains the number of recorded paths or why repository state was unavailable
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/worktree.py::DirtyAtStart.notes` @67086ecf5f6c
