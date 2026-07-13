---
type: concept
slug: workspace-volume-file-list-reader
title: Workspace volume file-list reader
---
# Workspace volume file-list reader

Workspace volume file-list reader is the fallback implementation used by the [serve workspace file list](../http/groom.md#serve-workspace-file-list) invocation when the connected sidecar cannot provide [workspace file list data](../workspace-file-list-data.md). It is the [Groom Docker I/O module](groom-docker-io-module.md) detail for [list-files](groom-docker-io-module.md#list-files): it delegates process execution to the [Docker subprocess runner](docker-subprocess-runner.md), reads one selected checkout inside a known workspace Docker volume through a shell-free, read-only Docker command, and returns repo-relative file paths without mutating the workflow container or broadcasting dashboard updates.

- code: groom/groom/docker_io.py::list_files
- verify: groom/tests/test_docker_io.py::test_list_files_returns_repo_relative_paths_and_prunes_vendor_dirs,
  groom/tests/test_docker_io.py::test_list_files_volume_root_when_repo_dir_empty,
  groom/tests/test_docker_io.py::test_list_files_empty_on_docker_failure

## Contract

- purpose: provide a volume-read fallback for dashboard file-tree requests when the live sidecar socket is absent, failed, or errored.
- input: `volume` is the Docker volume name mounted read-only at `/vol` for the duration of the read.
- input: `repo_dir` is a volume-relative checkout directory; `""` selects the workspace volume root.
- base path: when `repo_dir` is non-empty, the reader searches `/vol/{repo_dir}` after stripping only a trailing slash from the assembled base; otherwise it searches `/vol`.
- input trust boundary: `repo_dir` is not passed through the workspace-volume relative-path guard; the caller is responsible for supplying either `""` or a repository directory produced by Groom's repository selection flow.
- command: runs `docker run --rm -v {volume}:/vol:ro alpine:3.20 find {base} ( -type d ( -name .git -o -name node_modules -o -name __pycache__ -o -name .venv ) -prune ) -o ( -type f -print )`.
- output: returns `list[str]` containing file paths relative to the selected checkout root.
- parsing: only stdout lines beginning with `{base}/` are retained, and the returned value drops that prefix so Docker mount paths are never exposed to the dashboard.
- ignored output: blank lines and any `find` stdout line outside the selected base prefix are ignored.
- ordering: returned paths are sorted ascending for a stable tree order.
- pruning: directories named `.git`, `node_modules`, `__pycache__`, and `.venv` are excluded from traversal.
- timeout: the Docker process uses the module default 20-second timeout.
- failure: any non-zero Docker reader process returns an empty list rather than raising to the HTTP handler.
- exceptions: process-launch and timeout exceptions are not converted by this reader; callers that need to recover from those exceptions must do so outside this function.
- side effects: creates only a throwaway read-only Docker container for the read; it does not change files, workflow state, sidecar registry state, or dashboard clients.

## Fields

### field-selected-base-path

- type: absolute path inside the temporary container
- default: `/vol` when `repo_dir == ""`; otherwise `/vol/{repo_dir}` with a trailing slash stripped from the assembled path.
- required: true
- meaning: root whose descendant regular files become returned path entries.
- constraints: this reader does not validate or normalize `repo_dir` beyond the trailing-slash removal; callers provide the value from Groom's repository selection flow or an empty root selection.

### field-output-prefix

- type: absolute path prefix string inside the temporary container
- default: `field-selected-base-path + "/"`
- required: true
- meaning: stdout line prefix required before a `find` result is converted into returned workspace file-list data.
- constraints: a stripped stdout line that does not start with this prefix is ignored; the prefix itself is removed from accepted lines so the caller never receives `/vol`-absolute paths.

### field-skipped-directory-names

- type: `tuple[str, ...]`
- default: `(".git", "node_modules", "__pycache__", ".venv")`
- required: true
- code: groom/groom/docker_io.py::_SKIP_DIRS
- meaning: directory basenames pruned from traversal before file output is collected.
- constraints: this is the same skip set exposed by the [Groom Docker I/O module skip dirs field](groom-docker-io-module.md#field-skip-dirs) and keeps fallback file-list data aligned with the sidecar tree reader's vendor and VCS exclusions.

### field-container-image

- type: Docker image reference string
- default: `alpine:3.20`
- required: true
- code: groom/groom/docker_io.py::ALPINE_IMAGE
- meaning: minimal image used for the throwaway read-only `find` process.
- constraints: the image must provide BusyBox-compatible `find` with `-prune` and `-print` behavior.

### field-command-timeout

- type: `int`
- default: `20`
- required: true
- code: groom/groom/docker_io.py::DOCKER_TIMEOUT
- meaning: maximum seconds allowed for the Docker command through the shared runner.
- constraints: a timeout exception from the subprocess layer is not converted by this reader.

## Effects

- Builds: a selected base path under `/vol` from the requested repository directory, preserving `/vol` exactly for the workspace-root case.
- Builds: a `find` prune expression from the skipped directory names, joining multiple directory-name tests with `-o`.
- Calls: the [Docker subprocess runner](docker-subprocess-runner.md) once with a tokenized `docker run --rm -v <volume>:/vol:ro alpine:3.20 find <base> ... -type f -print` argv list.
- Scans: regular files reachable below the selected base after skip-directory pruning.
- Converts: any non-zero Docker process return code to `[]` because the HTTP file-list endpoint can render an empty Files panel.
- Parses: stdout line by line, stripping surrounding whitespace from each line.
- Emits: only stripped stdout lines beginning with `<base>/`, with that prefix removed so callers receive paths relative to the selected checkout root.
- Ignores: blank lines, Docker noise, warnings, and any stdout path outside the selected base prefix.
- Sorts: retained relative paths ascending before returning them.
- Preserves: file contents, directory contents, skipped directory contents, Docker volumes, workflow containers, registry state, sidecar sessions, and dashboard clients.

## Algorithms

### algorithm-file-list-read

- step: Resolve the selected base to `/vol` when `repo_dir` is empty, otherwise to `/vol/{repo_dir}` after trimming only trailing slash characters from the assembled base string.
- step: Construct a `find` prune predicate that matches every skipped directory basename.
- step: Run one temporary container with the workspace volume mounted read-only at `/vol` and the configured Alpine image as the command image.
- step: In that container, prune skipped directories and print every remaining regular file path below the selected base.
- step: If the Docker process exits non-zero, return an empty list.
- step: For each stdout line, strip surrounding whitespace.
- step: Keep only lines whose stripped text begins with the selected base plus `/`.
- step: Remove the selected-base prefix from each retained line.
- step: Return the retained relative paths sorted ascending.

## Failure behavior

- Docker command failure: returns `[]` for any non-zero process return code.
- Empty selected tree: returns `[]` when the Docker command succeeds but prints no matching regular files.
- Unexpected stdout line: ignores a line that is empty after stripping or does not begin with the selected base prefix.
- Missing selected base: represented as the Docker command's non-zero return and converted to `[]`.
- Process launch failure: not converted by this reader; launch exceptions from the subprocess runner propagate to the caller.
- Timeout: not converted by this reader; timeout exceptions from the subprocess runner propagate to the caller.

## Methods

### list-files

- sig: `list_files(volume: str, repo_dir: str = "") -> list[str]`
- abstract: false
- raises: propagates process launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md); converts Docker process return-code failures to an empty list.
- returns: sorted list of selected-root-relative file paths; an empty list means the selected tree is empty, the Docker process exited non-zero, or no stdout paths matched the selected base prefix.
- code: groom/groom/docker_io.py::list_files
- verify: groom/tests/test_docker_io.py::test_list_files_returns_repo_relative_paths_and_prunes_vendor_dirs
- verify: groom/tests/test_docker_io.py::test_list_files_volume_root_when_repo_dir_empty
- verify: groom/tests/test_docker_io.py::test_list_files_empty_on_docker_failure
- args:
  - `volume`: Docker volume name to mount at `/vol` read-only.
  - `repo_dir`: volume-relative checkout directory to list; `""` selects the volume root; callers are responsible for supplying a bounded repository selection because this reader does not apply the relative-path guard.
- does:
  - Builds the selected base path from `/vol` plus `repo_dir`, preserving the root case as exactly `/vol`.
  - Builds the prune expression from the shared skip directory names `.git`, `node_modules`, `__pycache__`, and `.venv`.
  - Delegates process execution to the [Docker subprocess runner](docker-subprocess-runner.md).
  - Runs one read-only `alpine:3.20` container with `find` to print non-pruned regular files.
  - Converts only matching absolute mount paths into paths relative to the selected base.
  - Sorts the resulting list before returning it.
