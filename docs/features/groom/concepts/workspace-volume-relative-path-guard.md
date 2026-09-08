---
type: concept
slug: workspace-volume-relative-path-guard
title: Workspace volume relative path guard
---
# Workspace volume relative path guard

Workspace volume relative path guard is the validation layer used by the [workspace volume file-content reader](workspace-volume-file-content-reader.md), the [workspace volume file writer](workspace-volume-file-writer.md), and the [gate-answering layer](gate-answering-layer.md) before a dashboard-selected or gate-selected path is embedded in a Docker volume destination. It accepts only one non-empty path inside the mounted workspace volume, normalizes Windows-style separators to `/`, and rejects absolute paths, empty path segments, and parent traversal before any Docker container, file read, file write, workflow-state mutation, or dashboard update can occur.

- code: groom/groom/docker_io.py::safe_relpath
- detail: [safe relpath documentation views](safe-relpath-documentation-views.md)
- refs: [workspace volume file-content reader](workspace-volume-file-content-reader.md), [workspace volume file writer](workspace-volume-file-writer.md), [gate-answering layer](gate-answering-layer.md), [workspace file content data](../workspace-file-content-data.md), [operator gate context file](../operator-gate-context-file.md)

## Contract

- purpose: constrain caller-provided volume paths to a single relative path rooted inside the mounted workspace volume.
- input: `path` is a required `str` supplied by an HTTP query, gate file reference, or caller-composed repository/file path before it is used as a `/vol/...` Docker container path; callers own any conversion from external values to text before invoking the guard.
- acceptance: accepts paths that are non-empty, do not begin with `/` or `\\`, and contain no empty segment and no `..` segment after `\\` characters are treated as `/` separators.
- acceptance: accepts ordinary file names, nested relative paths such as `repo/src/file.py`, Windows-separator equivalents such as `repo\\src\\file.py`, `.` segments, `...` segments, spaces, colons, and shell metacharacters; those characters are not interpreted by this guard.
- consistency: field-return-value — accepted backslash separators are replaced with `/` in the returned normalized path.
- verify: omits(subject="accepted normalized path", text="\\")
- output: returns the normalized relative path string; the returned value never starts with `/`, never starts with `\\`, never contains `//`, never contains an empty segment, and never contains `..` as a segment.
- idempotence: any accepted output can be passed to the guard again and is returned unchanged.
- failure: raises `ValueError` with an `unsafe path: ...` message when the input is empty, begins with `/`, begins with `\\`, contains adjacent separators, ends with a separator, or contains a parent traversal segment exactly equal to `..`.
- boundary: does not perform existence, file-vs-directory, permission, Docker-volume, encoding, symlink, repository-membership, current-directory collapse, or maximum-length checks; callers and Docker operations own those outcomes after a path passes this syntactic guard.
- caller contract: first-party readers and writers must use the returned normalized path, not the original input, when building `/vol/{path}` destinations.
- non-effect: does not touch Docker, the filesystem, workflow state, sidecar connections, dashboard clients, logs, or network sockets; it only validates and normalizes the string.

## Fields

### field-path

- type: `str`
- default: none
- required: true
- semantics: caller-supplied workspace-volume path before a Docker-volume file operation embeds it below `/vol`.
- semantics: acceptance requires a non-empty relative path whose first character is neither `/` nor `\`.
- semantics: acceptance requires a normalized segment list with no empty segment and no segment exactly equal to `..`.
- semantics: every `\` character is treated as a separator and converted to `/` before segment checks complete.
- semantics: the guard does not check non-string coercion, file existence, file type, symlink resolution, repository membership, Docker volume name, permissions, encoding, or maximum length.
- verify: omits(subject="accepted normalized path", text="..")
- verify: omits(subject="accepted normalized path", text="\\")

### field-return-value

- type: `str`
- default: none
- required: true
- semantics: normalized volume-relative path that callers may append to `/vol/` for the Docker container destination.
- semantics: the returned path is non-empty and does not start with `/` or `\`.
- semantics: the returned path has no empty segment or `..` segment and uses `/` as its only separator.
- semantics: accepted segment text is preserved except for separator normalization, including `.`, `...`, spaces, colons, shell metacharacters, and other ordinary filename characters.
- verify: omits(subject="returned normalized path", text="..")
- verify: omits(subject="returned normalized path", text="\\")

## Methods

### safe-relpath

- sig: `safe_relpath(path: str) -> str`
- abstract: false
- does: validates one [field-path](#field-path) value before a Docker volume reader or writer embeds it below `/vol`.
- does: returns the `/`-normalized accepted path without collapsing `.` segments or otherwise changing accepted segment text.
- does: raises `ValueError` using `unsafe path: {path!r}` for a rejected path.
- does: performs no I/O or mutation.
- verify: omits(subject="accepted normalized path", text="..")
- verify: omits(subject="accepted normalized path", text="\\")
- raises: `ValueError` for empty, leading-root, empty-segment, trailing-separator, or parent-traversal paths.
- returns: [field-return-value](#field-return-value) on acceptance.
- code: groom/groom/docker_io.py::safe_relpath
- detail: [safe relpath documentation views](safe-relpath-documentation-views.md)

#### Effects

- consistency: field-path — rejects unsafe [field-path](#field-path) values before a caller can build a Docker container path.
- normalizes: converts accepted backslash separators to `/` and returns the joined segment list.
- blocks: absolute-root escapes, parent-directory escapes, accidental path collapse through adjacent separators, and empty/trailing destination segments.
- permits: literal current-directory segments, literal triple-dot segments, spaces, punctuation, colons, and shell metacharacters because Docker callers pass argv lists rather than shell command strings.
- does not call: Docker, subprocess, filesystem, network, sidecar, workflow-state, or dashboard APIs.

## Algorithm

- consistency: field-path — `safe_relpath` rejects empty paths and paths beginning with `/` or `\\` rather than returning a normalized volume-relative path.
- verify: omits(subject="accepted normalized path", matches="^(?:/|\\\\)")
- step: Convert every `\\` character to `/` so later segment checks use one separator model.
- step: Split the normalized path on `/`.
- step: Reject the path when any segment is empty, which covers adjacent separators and a trailing separator.
- step: Reject the path when any segment is exactly `..`, so callers cannot escape the mounted volume root.
- step: Return the normalized segments joined by `/`.

## Examples

- consistency: field-return-value — `docs/gate.md` is returned unchanged.
- verify: unchanged(subject="accepted docs/gate.md path")
- consistency: field-return-value — `repo\\src\\file.py` is returned as `repo/src/file.py`.
- verify: omits(subject="accepted normalized path", text="\\")
- consistency: field-return-value — `repo/./file.py` is returned unchanged.
- verify: unchanged(subject="accepted current-directory path")
- consistency: field-return-value — the guard preserves literal current-directory markers in the normalized path.
- verify: unchanged(subject="normalized path with current-directory marker")
- rejects: the empty string raises `ValueError`.
- rejects: `/etc/passwd` raises `ValueError`.
- rejects: `\\etc\\passwd` raises `ValueError`.
- rejects: `repo//file.py` raises `ValueError`.
- rejects: `repo/file.py/` raises `ValueError`.
- rejects: `repo/../secret.txt` raises `ValueError`.

## Consumers

- uses: [workspace volume file-content reader](workspace-volume-file-content-reader.md) validates the fallback file-content path before it starts a read-only Docker container.
- uses: [workspace volume file writer](workspace-volume-file-writer.md) validates the gate-answer destination path before it starts a read-write Docker container.
- uses: [gate-answering layer](gate-answering-layer.md) reaches the same guard through the Docker volume file helpers when it reads and writes gate files.
