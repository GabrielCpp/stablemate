---
type: concept
slug: sidecar-local-relative-path-guard
title: Sidecar-local relative path guard
---
# Sidecar-local relative path guard

Sidecar-local relative path guard is the sidecar data-plane validation layer used by [workspace file content data](../workspace-file-content-data.md) before a `getFile` RPC reads from the sidecar container's local workspace mount. It mirrors the path-safety contract of the [workspace volume relative path guard](workspace-volume-relative-path-guard.md) for local sidecar reads: accept one non-empty relative path, normalize Windows separators to `/`, and reject absolute paths, empty path segments, and parent traversal before any local file read can occur. Unsafe paths are raised as `ValueError` by the guard, then surface through the [sidecar websocket frame](../sidecar-websocket-frame.md) RPC failure contract as an `ok=false` `rpc_result` handled by the [sidecar connected session](sidecar-connected-session.md).

- code: groom/groom/sidecar.py::_safe_relpath
- verify: groom/tests/test_sidecar_session.py::test_safe_relpath_accepts_normal_and_rejects_traversal,
  groom/tests/test_sidecar_session.py::test_rpc_get_file_rejects_traversal,
  groom/tests/test_sidecar_session.py::test_handle_rpc_get_file_traversal_replies_error
- refs: [workspace file content data](../workspace-file-content-data.md), [workspace volume relative path guard](workspace-volume-relative-path-guard.md), [sidecar websocket frame](../sidecar-websocket-frame.md), [sidecar connected session](sidecar-connected-session.md)

## Contract

For accepted input, `_safe_relpath` replaces backslashes with `/` and joins the resulting
segments with `/`; this gives later local-path construction one separator convention.

- purpose: constrain caller-composed sidecar workspace paths to one syntactically relative path rooted below the sidecar's local workspace directory before the file-content RPC reads from disk.
- input: `path` is the composed workspace-relative string used by `getFile`; the RPC handler has already converted `repo` and `path` request parameters to strings, combined them, and skipped validation when the composed path is empty.
- acceptance: accepts non-empty paths that do not begin with `/` or `\\`, and whose separator-normalized segments contain no empty string and no `..` segment.
- acceptance: accepts ordinary nested relative file paths such as `repo/src/a.py`, Windows-separator equivalents such as `repo\\src\\a.py`, `.` segments, `...` segments, spaces, colons, and shell metacharacters; those characters are not interpreted by this guard.
- output: returns the normalized relative path string; the returned value never starts with `/`, never starts with `\\`, never contains `//`, never contains an empty segment, and never contains `..` as a segment.
- idempotence: an already-normalized accepted output is accepted unchanged by a later guard call.
- failure: raises `ValueError` with an `unsafe path: ...` message when the input is empty, begins with `/`, begins with `\\`, contains adjacent separators, ends with a separator, or contains a parent traversal segment exactly equal to `..`.
- failure: does not convert unsafe input into empty content; the sidecar RPC wrapper converts the raised exception into an error `rpc_result`, allowing the host endpoint to fall back to volume reading when available.
- non-effect: does not touch the filesystem, Docker, Git, workflow state, sidecar registrations, dashboard clients, websocket I/O, or logs; it only validates and normalizes the supplied string.
- boundary: does not perform existence, file-vs-directory, permission, encoding, repository-membership, symlink, maximum-length, or current-directory-segment collapse checks; those outcomes belong to the file read that follows a successful validation.

## Methods

### method-_safe_relpath

- sig: `_safe_relpath(path: str) -> str`
- abstract: false
- raises: `ValueError` for empty, leading-root, empty-segment, trailing-separator, or parent-traversal paths.
- verify: count(subject="unsafe path inputs rejected by _safe_relpath", equals=5)
- code: groom/groom/sidecar.py::_safe_relpath
- tests: groom/tests/test_sidecar_session.py::test_safe_relpath_accepts_normal_and_rejects_traversal
- input: composed sidecar workspace-relative path string for a local data-plane read; callers must pass a string, not an arbitrary JSON value.
- output: normalized relative path string using `/` separators, suitable for appending below the sidecar's local workspace directory.
- invariant: accepted output is never absolute and never contains an empty or `..` path segment.
- failure-message: rejected paths use `unsafe path: {path!r}` as the exception message that the RPC wrapper relays in the websocket error result.
- non-effect: performs no I/O and no mutation.
- consumer: [workspace file content data](../workspace-file-content-data.md) method `_rpc_get_file` is the first-party caller.
- consistency: Before a local file read, the sidecar-local guard rejects a composed path that is empty or begins with `/` or `\\`.
- verify: count(subject="empty and rooted paths rejected by _safe_relpath", equals=3)

## Algorithm

- step: Receive the already-composed sidecar workspace-relative path string from the file-content RPC handler.
- step: Convert every `\\` character to `/` so segment checks use one separator model.
- step: Split the normalized path on `/`.
- step: Reject the path when any segment is empty, which covers adjacent separators and a trailing separator.
- step: Reject the path when any segment is exactly `..`, which blocks parent traversal out of the workspace root.
- step: Return the accepted segments joined by `/`.

## Examples

- consistency: `_safe_relpath` returns `acme/src/a.py` unchanged for the accepted `acme/src/a.py` input.
- verify: count(subject="accepted _safe_relpath paths unchanged after normalization", equals=1)
- consistency: `_safe_relpath` returns `acme/src/a.py` for the accepted `acme\\src\\a.py` input.
- verify: count(subject="accepted backslash-separated _safe_relpath paths normalized to slash separators", equals=1)
- consistency: `_safe_relpath` preserves the `.` segment in accepted `acme/./a.py` input while returning `acme/./a.py`.
- verify: count(subject="accepted _safe_relpath paths retaining current-directory segments", equals=1)
- rejects: the empty string raises `ValueError` when passed directly to the guard.
- rejects: `/etc/passwd` raises `ValueError`.
- rejects: `\\etc\\passwd` raises `ValueError`.
- rejects: `repo//file.py` raises `ValueError`.
- rejects: `repo/file.py/` raises `ValueError`.
- rejects: `repo/../secret.txt` raises `ValueError`.

## Consumers

- uses: [workspace file content data](../workspace-file-content-data.md) calls this guard from `method-_rpc_get_file` after composing a sidecar-local read path and before reading `WORKSPACE_DIR / normalized_path`.
- consistency: [sidecar connected session](sidecar-connected-session.md) catches the guard's `ValueError` through the RPC dispatch path and emits one [sidecar websocket frame](../sidecar-websocket-frame.md) `rpc_result` error instead of terminating the persistent socket session.
- verify: emitted(event="rpc_result error for a rejected sidecar path", count=1)
- compares-with: [workspace volume relative path guard](workspace-volume-relative-path-guard.md) provides the same syntactic path-safety contract for fallback Docker-volume reads and writes outside the sidecar-local filesystem.
