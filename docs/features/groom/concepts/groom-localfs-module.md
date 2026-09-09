---
type: concept
slug: groom-localfs-module
title: Groom local-filesystem module
---
# Groom local-filesystem module

Groom local-filesystem module is the native-run local-filesystem adapter for the [groom server](../http/groom.md) and [groom sidecar](../groom-sidecar.md) control plane: it centralizes same-host workspace and run directory reads, live process state checks, file-content reads and writes, and repository discovery without Docker. Every function reads directly from the host's filesystem — no throwaway container, no volume mount, no docker at all — and mirrors the [groom Docker I/O module](groom-docker-io-module.md) signatures so handlers branch on `WorkflowContainer.native` and call one or the other with the same shape. Its public helpers exchange [workspace file list data](../workspace-file-list-data.md), [workspace file content data](../workspace-file-content-data.md), and [workspace diff data](../workspace-diff-data.md) without owning workflow registry state, dashboard rendering, sidecar websocket state, or gate-answer orchestration. Every function is best-effort — a bad base path yields an empty result, never a raise — because a diff/tree panel is a nice-to-have, not on any critical path.

- code: groom/groom/localfs.py
- extends: [groom Docker I/O module](groom-docker-io-module.md)
- tests: groom/tests/test_app.py::test_diff_endpoint_returns_empty_when_native_run_not_found
- tests: groom/tests/test_app.py::test_file_content_endpoint_returns_empty_when_native_run_not_found

Path safety is shared with [groom Docker I/O module](groom-docker-io-module.md) via its `safe_relpath` guard; the skip set (`_SKIP_DIRS`) matches Docker volume scanning so both paths agree on what a checkout's tree contains. The module does not launch Docker or mutate local files except through [write-file](#write-file), which is the same boundary as docker_io.

## Contract

- public surface: the module exposes nine public helpers: [is-local-dir](#is-local-dir), [run-terminal](#run-terminal), [pid-alive](#pid-alive), [list-files](#list-files), [list-repo-dirs](#list-repo-dirs), [find-repo-dir](#find-repo-dir), [git-diff](#git-diff), [read-file](#read-file), and [write-file](#write-file).
- path safety: helpers that accept file paths inside the base call [safe-relpath](groom-docker-io-module.md#safe-relpath) (imported from docker_io) before constructing absolute paths; helpers that accept base paths or repository directories assume those values have already been bounded by upstream UI selection or file existence checks.
- state ownership: the module stores no workflow containers, gate records, run metadata, or dashboard state.
- execution environment: the module runs in groom's host process and reads the host filesystem, host process table, and host git repositories directly.

Every function is best-effort — a bad base path, missing run record, unreachable process, or filesystem read failure yields the zero value for its return type (`False`, `""`, `[]`, or `None`), never a raise.

Every helper that mirrors [groom Docker I/O module](groom-docker-io-module.md) accepts the same arguments in the same order and returns the same shape; the first argument is positional-only in both modules, named after its own concept (a host base path here, a volume name there).

## Public Helper Matrix

Container and workflow operation includes [is-local-dir](#is-local-dir) to detect native-run basis, [run-terminal](#run-terminal) to read the run's final state, and [pid-alive](#pid-alive) to check if the runner process still lives.

Workspace-volume reads are [list-files](#list-files), [list-repo-dirs](#list-repo-dirs), [find-repo-dir](#find-repo-dir), [git-diff](#git-diff), and [read-file](#read-file); what each one returns is the normative `returns:`/`verify:` claim under that helper's own entry in [Methods](#methods).

File write is [write-file](#write-file) only, for gate-file answers.

## Argument Ownership

- base: host-absolute path to the run's checked-out workspace root. This is the [workflow container](workflow-container.md)'s `workspace_volume` field for a native run; the module tests it for readability and uses it to anchor all relative paths.
- repo_dir: optional base-relative repository directory; empty means the workspace root or the first discovered checkout. Passed to [list-files](#list-files) and [git-diff](#git-diff) unchanged after path-safety validation.
- rel_path: caller-selected base-relative path for [read-file](#read-file) and [write-file](#write-file), validated by [safe-relpath](groom-docker-io-module.md#safe-relpath).
- content: text payload for [write-file](#write-file); passed directly to file-write operations.
- run_dir: host-absolute path to the workflow run's artifact directory, where `run.json` and other metadata live.
- pid: integer process id for [pid-alive](#pid-alive) to check via signal 0 and `/proc` state inspection.

## Return Conventions

Each helper returns a specific shape: boolean for existence/readiness checks, strings or empty for text results, lists for discovery results, and `None` or `False` for failure states. Specifics are documented under each method's `returns:` bullet and verified by its `verify:` checks.

## Fields

### field-skip-dirs

- type: `tuple[str, ...]`
- default: `(".git", "node_modules", "__pycache__", ".venv")`
- code: groom/groom/docker_io.py::_SKIP_DIRS
- detail: [workspace volume skip directory names](workspace-volume-skip-directory-names.md)
- meaning: directory names to skip when recursively walking a checkout tree for file listing or diff analysis. Imported from [groom Docker I/O module](groom-docker-io-module.md) so native and docker-volume readers agree on tree content.

### field-docker-timeout

- type: `int`
- default: `20`
- code: groom/groom/docker_io.py::DOCKER_TIMEOUT
- detail: [Docker command timeout](docker-command-timeout.md)
- meaning: default maximum seconds a git subprocess may run before raising a timeout exception. Imported from [groom Docker I/O module](groom-docker-io-module.md) and used by [git-diff](#git-diff).

## Methods

### _base

- sig: `_base(base: str, repo_dir: str = "") -> Path | None`
- abstract: false
- raises: no exception for unreadable or missing paths.
- verify: json_path(path="exception.type", absent=true)
- returns: resolved checkout root directory path when readable, or `None` for unreadable or missing base.
- code: groom/groom/localfs.py::_base
- input: `base` is the run's host-absolute workspace root; `repo_dir` is an optional base-relative checkout directory, validated and normalized by [safe-relpath](groom-docker-io-module.md#safe-relpath).
- output: a Path object pointing to the checkout root, or `None`.
- resolution: joins `base` and `repo_dir` if both are supplied; returns `None` if the result is not a readable directory.
- effects: reads only the filesystem's directory metadata; does not read file contents, launch processes, mutate files, or inspect the git tree.
- algorithm:
  1. Return `None` immediately if `base` is empty.
  2. Resolve `base` to a Path object.
  3. If `repo_dir` is supplied, append it to the path after passing through [safe-relpath](groom-docker-io-module.md#safe-relpath) validation.
  4. Return the path if it is a readable directory; otherwise return `None`.

### is-local-dir

- sig: `is_local_dir(path: str) -> bool`
- abstract: false
- raises: no exception.
- verify: json_path(path="exception.type", absent=true)
- returns: `True` when path is a readable directory on the host, `False` otherwise.
- code: groom/groom/localfs.py::is_local_dir
- input: `path` is a host filesystem path string.
- output: boolean indicating whether the path exists as a readable directory.
- use case: the signal that a workflow run is native (its run directory exists on this host) rather than containerized.
- effects: reads only filesystem directory metadata; does not read contents, launch processes, or mutate anything.

### run-terminal

- sig: `run_terminal(run_dir: str, /) -> str`
- abstract: false
- raises: no exception for missing or unreadable `run.json`.
- verify: json_path(path="exception.type", absent=true)
- returns: the run's `terminal` field from `run.json`, or empty string `""` when the file is missing, unreadable, malformed, or contains no terminal value.
- code: groom/groom/localfs.py::run_terminal
- input: `run_dir` is the run's host-absolute artifact directory.
- output: the terminal state string, or `""`.
- effects: reads the host filesystem and parses JSON; does not launch processes, mutate files, inspect docker, or update workflow state.

### pid-alive

- sig: `pid_alive(pid: int) -> bool`
- abstract: false
- raises: no exception.
- verify: json_path(path="exception.type", absent=true)
- returns: `True` when the process with this pid still exists and is in a running state, `False` otherwise.
- code: groom/groom/localfs.py::pid_alive
- input: `pid` is an integer process id, typically from a run record's launcher pid.
- output: boolean indicating whether the process is running.
- signal method: uses `os.kill(pid, 0)` to test for existence without delivering a signal; `EPERM` means the process exists but is owned by another user, which counts as alive for this check.
- zombie handling: signal 0 alone reports a killed process with an unreaping parent as healthy; the function additionally reads `/proc/{pid}/stat` to check the state code and excludes zombies (`Z` state). Where procfs is unavailable, existence is the best answer available.
- use case: determining whether a native-run orchestrator process still has work in flight; critical for runs that died mid-flush or were not yet reaped by their parent.
- effects: sends signal 0 to the process and reads `/proc` state when available; does not send any other signal, mutate filesystem, launch docker, or update workflow state.

### list-files

- sig: `list_files(base: str, /, repo_dir: str = "") -> list[str]`
- abstract: false
- raises: no exception.
- verify: json_path(path="exception.type", absent=true)
- returns: sorted list of repo-relative file paths, or `[]` when the base is unreadable, missing, or empty.
- code: groom/groom/localfs.py::list_files
- input: `base` is the run's host-absolute workspace root; `repo_dir` is an optional base-relative checkout directory.
- output: sorted file paths relative to the selected checkout.
- repository resolution: delegates to [_base](#_base) to resolve the checkout root; returns `[]` if resolution fails.
- pruning: skips any directory named `.git`, `node_modules`, `__pycache__`, or `.venv` during the tree walk.
- path normalization: returned paths use forward slashes as separators, regardless of host OS, for consistent wire representation.
- consumer: used by the Files pane to render the repository tree; also consumed by [workspace file list data](../workspace-file-list-data.md).
- effects: walks the host filesystem tree; reads only metadata and does not read file contents, launch processes, mutate files, or call docker.
- algorithm:
  1. Resolve the checkout root with [_base](#_base); return `[]` if it fails.
  2. Recursively walk the resolved root, filtering out skipped directory names.
  3. For each discovered file, compute its path relative to the checkout root.
  4. Collect and sort all relative paths ascending.
  5. Return the sorted list.

### list-repo-dirs

- sig: `list_repo_dirs(base: str, /) -> list[str]`
- abstract: false
- raises: no exception.
- verify: json_path(path="exception.type", absent=true)
- returns: sorted list of base-relative git checkout directory names, or `[]` when the base is unreadable or contains no checkouts.
- code: groom/groom/localfs.py::list_repo_dirs
- input: `base` is the run's host-absolute workspace root.
- output: sorted base-relative checkout directory names, including `""` for the workspace root itself when it is a git checkout.
- discovery scope: checks the workspace root for a `.git` directory; checks immediate children for `.git` directories, skipping directories in the skip set.
- discovery depth: does not recurse below immediate children; a nested checkout under a child checkout is discovered as a `.git` inside the first child.
- empty-state behavior: returns `[]` when base is unreadable; returns `[""]` for a workspace root that is a git checkout but has no child checkouts; returns child names only (no `""`) when child checkouts exist but the root is not a checkout.
- repository selection: workspace root is represented as `""`; child checkouts are represented by child directory name only. Later repository selection (e.g., in diff handlers) passes these values to [_base](#_base) to resolve them to paths.
- consumer: used by diff and file-list handlers to enumerate available checkouts for the repository picker; also used by git-diff defaulting when no repository is specified.
- effects: reads only filesystem directory metadata; does not read file contents, launch git, mutate files, or call docker.
- algorithm:
  1. Resolve the workspace root with [_base](#_base); return `[]` if it fails.
  2. Check whether the workspace root itself contains a `.git` directory; if so, start candidates with `""`.
  3. Iterate immediate children of the workspace root.
  4. Skip any child in the skip set.
  5. Include a child name as a candidate only if the child is a directory and contains a `.git` directory.
  6. Return sorted candidates ascending, or `[""]` if only the root is a checkout.

### find-repo-dir

- sig: `find_repo_dir(base: str) -> str`
- abstract: false
- raises: no exception.
- verify: json_path(path="exception.type", absent=true)
- returns: the name of the first discovered checkout directory, or `""` when no child checkouts exist.
- code: groom/groom/localfs.py::find_repo_dir
- input: `base` is the run's host-absolute workspace root.
- output: base-relative checkout directory name (non-empty only), or empty string.
- repository selection: first result of [method-list-repo-dirs](#list-repo-dirs) after filtering out `""`.
- use case: defaulting for diff extraction when no repository is specified; picks a checkout automatically so an operator can read the diff without first choosing a repository.
- effects: reads only filesystem directory metadata; does not read contents, launch git, or mutate anything.

### git-diff

- sig: `git_diff(base: str, /, repo_dir: str = "") -> str`
- abstract: false
- raises: no exception for missing checkout or non-zero git exit.
- verify: json_path(path="exception.type", absent=true)
- returns: raw unified working-tree-versus-HEAD diff text, or `""` when no checkout resolves or git exits non-zero.
- code: groom/groom/localfs.py::git_diff
- input: `base` is the run's host-absolute workspace root; `repo_dir` is an optional base-relative checkout directory.
- output: raw git diff stdout or empty string.
- repository selection: resolves `base/repo_dir` first with [_base](#_base); when that fails and no `repo_dir` was supplied, calls [method-find-repo-dir](#find-repo-dir) and resolves again.
- command: runs host-local `git -c safe.directory=* -C <selected checkout> diff HEAD` with captured text stdout and the shared [DOCKER_TIMEOUT](#field-docker-timeout) timeout.
- timeout: maximum of [field-docker-timeout](#field-docker-timeout) seconds to allow the git process to run.
- failure behavior: process launch failures, subprocess exceptions, timeout exceptions, and non-zero git exit all return `""`.
- consumer: used by the Changes pane to show working-tree differences; also consumed by [workspace diff data](../workspace-diff-data.md).
- parity: returns the same string the Docker-volume reader would for the same checkout, which is what lets the endpoint pick between them by a boolean and return one shape.
- detail: [native git diff documentation scope](native-git-diff-documentation-scope.md)
- effects: reads the host filesystem and launches a read-only git subprocess; does not mutate files, touch docker, send sidecar frames, or update workflow/dashboard state.
- algorithm:
  1. Resolve the checkout root with [_base](#_base).
  2. If resolution fails and no `repo_dir` was supplied, call [method-find-repo-dir](#find-repo-dir) and resolve again.
  3. If the second attempt also fails, return `""`.
  4. Launch `git -c safe.directory=* -C <selected checkout> diff HEAD` with captured stdout and a [field-docker-timeout](#field-docker-timeout) timeout.
  5. If the command exits non-zero, return `""`.
  6. Return stdout unchanged.

### read-file

- sig: `read_file(base: str, /, rel_path: str) -> str | None`
- abstract: false
- raises: no exception.
- verify: json_path(path="exception.type", absent=true)
- returns: the file's text contents when readable, or `None` when the file is missing, unreadable, or the path is unsafe.
- code: groom/groom/localfs.py::read_file
- input: `base` is the run's host-absolute workspace root; `rel_path` is a relative path within the base, validated by [safe-relpath](groom-docker-io-module.md#safe-relpath).
- output: file text or `None`.
- path safety: the relative path is validated against directory traversal before file access; a crafted path with `..` or `/` escapes raises `ValueError`, which is caught and returns `None`.
- effects: reads the host filesystem; does not mutate files, launch processes, call docker, or update workflow/dashboard state.
- use case: reading gate-answer files written by the sidecar or previous workflow steps.

### write-file

- sig: `write_file(base: str, /, rel_path: str, content: str) -> bool`
- abstract: false
- raises: no exception.
- verify: json_path(path="exception.type", absent=true)
- returns: `True` when the file is written successfully to disk.
- returns: `False` when the file write fails for any reason.
- code: groom/groom/localfs.py::write_file
- input: `base` is the run's host-absolute workspace root; `rel_path` is a relative path, validated by [safe-relpath](groom-docker-io-module.md#safe-relpath); `content` is the text to write.
- output: boolean indicating whether the write completed.
- path safety: the relative path is validated against directory traversal; an unsafe path raises `ValueError`, which is caught and returns `False`.
- directory creation: parent directories are created with `mkdir(parents=True, exist_ok=True)` to ensure the target directory exists.
- write behavior: replaces the entire file; does not append or merge with existing content.
- failure handling: any `OSError` from directory creation or file write returns `False`.
- effects: writes exactly one file under the base; does not delete files, launch processes, call docker, or update workflow/dashboard state.
- use case: writing gate-answer files so the workflow's next stage can read them.

