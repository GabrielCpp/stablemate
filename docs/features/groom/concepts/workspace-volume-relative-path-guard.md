---
type: concept
slug: workspace-volume-relative-path-guard
title: Workspace volume relative path guard
---
# Workspace volume relative path guard

Workspace volume relative path guard is the validation layer used by the [workspace volume file-content reader](workspace-volume-file-content-reader.md), the [workspace volume file writer](workspace-volume-file-writer.md), and the [gate-answering layer](gate-answering-layer.md) before a dashboard-selected or gate-selected path is embedded in a Docker volume destination. It accepts only one non-empty path inside the mounted workspace volume, normalizes Windows-style separators to `/`, and rejects absolute paths, empty path segments, and parent traversal before any Docker container, file read, file write, workflow-state mutation, or dashboard update can occur.

- code: groom/groom/docker_io.py::safe_relpath
- refs: [workspace volume file-content reader](workspace-volume-file-content-reader.md), [workspace volume file writer](workspace-volume-file-writer.md), [gate-answering layer](gate-answering-layer.md), [workspace file content data](../workspace-file-content-data.md), [operator gate context file](../operator-gate-context-file.md)

## Contract

- purpose: constrain caller-provided volume paths to a single relative path rooted inside the mounted workspace volume.
- input: `path` is a required `str` supplied by an HTTP query, gate file reference, or caller-composed repository/file path before it is used as a `/vol/...` Docker container path; callers own any conversion from external values to text before invoking the guard.
- acceptance: accepts paths that are non-empty, do not begin with `/` or `\\`, and contain no empty segment and no `..` segment after `\\` characters are treated as `/` separators.
- acceptance: accepts ordinary file names, nested relative paths such as `repo/src/file.py`, Windows-separator equivalents such as `repo\\src\\file.py`, `.` segments, `...` segments, spaces, colons, and shell metacharacters; those characters are not interpreted by this guard.
- normalization: replaces every `\\` separator with `/` and returns the normalized `/`-joined segment list.
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
- meaning: caller-supplied workspace-volume path before it is embedded below `/vol` by a Docker-volume file operation.
- accepted: non-empty relative path whose first character is neither `/` nor `\` and whose normalized segment list contains no empty segment and no segment exactly equal to `..`.
- rejected: empty string, POSIX absolute path, backslash-rooted path, adjacent separators, trailing separator, and parent traversal segment.
- normalization: every `\` character is treated as a separator and converted to `/` before segment checks complete.
- not checked: non-string coercion, file existence, file type, symlink resolution, repository membership, Docker volume name, permissions, encoding, or maximum length.

### field-return-value

- type: `str`
- default: none
- required: true
- meaning: normalized volume-relative path that callers may append to `/vol/` for the Docker container destination.
- invariant: non-empty, does not start with `/` or `\`, contains no empty segment, contains no `..` segment, and uses `/` as its only separator.
- preservation: keeps accepted segment text exactly except for separator normalization, including `.`, `...`, spaces, colons, shell metacharacters, and other ordinary filename characters.

## Methods

### safe-relpath

- sig: `safe_relpath(path: str) -> str`
- abstract: false
- raises: `ValueError` for empty, leading-root, empty-segment, trailing-separator, or parent-traversal paths.
- returns: [field-return-value](#field-return-value) on acceptance.
- code: groom/groom/docker_io.py::safe_relpath
- args: `path`; required; no default; follows the [field-path](#field-path) contract.
- summary: validates and normalizes one workspace-volume relative path before any Docker volume read or write embeds it below `/vol`; accepted output is safe to concatenate as `/vol/{path}` because it cannot escape through an absolute prefix, an empty segment, or a `..` segment.
- invariant: accepted output is non-empty, relative, and contains no empty or `..` segment.
- failure-message: rejected paths use `unsafe path: {path!r}` in the raised `ValueError`.
- non-effect: performs no I/O and no mutation.
- consumers: [workspace volume file-content reader](workspace-volume-file-content-reader.md) and [workspace volume file writer](workspace-volume-file-writer.md) call this method before constructing the Docker container path under `/vol`.

#### Effects

- validates: rejects unsafe [field-path](#field-path) values before a caller can build a Docker container path.
- normalizes: converts accepted backslash separators to `/` and returns the joined segment list.
- blocks: absolute-root escapes, parent-directory escapes, accidental path collapse through adjacent separators, and empty/trailing destination segments.
- permits: literal current-directory segments, literal triple-dot segments, spaces, punctuation, colons, and shell metacharacters because Docker callers pass argv lists rather than shell command strings.
- does not call: Docker, subprocess, filesystem, network, sidecar, workflow-state, or dashboard APIs.

## Algorithm

- step: Reject the path immediately when it is empty, begins with `/`, or begins with `\\`.
- step: Convert every `\\` character to `/` so later segment checks use one separator model.
- step: Split the normalized path on `/`.
- step: Reject the path when any segment is empty, which covers adjacent separators and a trailing separator.
- step: Reject the path when any segment is exactly `..`, so callers cannot escape the mounted volume root.
- step: Return the normalized segments joined by `/`.

## Examples

- accepts: `docs/gate.md` returns `docs/gate.md`.
- accepts: `repo\\src\\file.py` returns `repo/src/file.py`.
- accepts: `repo/./file.py` returns `repo/./file.py`; this guard blocks traversal but does not collapse current-directory markers.
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
