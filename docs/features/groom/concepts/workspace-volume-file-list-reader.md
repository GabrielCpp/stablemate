---
type: concept
slug: workspace-volume-file-list-reader
title: Workspace volume file-list reader
---
# Workspace volume file-list reader

Workspace volume file-list reader is the fallback implementation used by the [serve workspace file list](../http/groom.md#serve-workspace-file-list) invocation when the connected sidecar cannot provide [workspace file list data](../workspace-file-list-data.md). It is the [Groom Docker I/O module](groom-docker-io-module.md) detail for [list-files](groom-docker-io-module.md#list-files): it delegates process execution to the [Docker subprocess runner](docker-subprocess-runner.md), reads one selected checkout inside a known workspace Docker volume through a shell-free, read-only Docker command, and returns repo-relative file paths without mutating the workflow container or broadcasting dashboard updates.

- code: groom/groom/docker_io.py::list_files
- tests: groom/tests/test_docker_io.py::test_list_files_returns_repo_relative_paths_and_prunes_vendor_dirs,
  groom/tests/test_docker_io.py::test_list_files_volume_root_when_repo_dir_empty,
  groom/tests/test_docker_io.py::test_list_files_empty_on_docker_failure
- detail: [List-files documentation views](list-files-documentation-views.md)

## Contract

- purpose: provide a volume-read fallback for dashboard file-tree requests when the live sidecar socket is absent, failed, or errored.
- input: `volume` is the Docker volume name mounted read-only at `/vol` for the duration of the read.
- input: `repo_dir` is a volume-relative checkout directory; `""` selects the workspace volume root.
- base path: when `repo_dir` is non-empty, the reader searches `/vol/{repo_dir}` after stripping only a trailing slash from the assembled base; otherwise it searches `/vol`.
- input trust boundary: `repo_dir` is not passed through the workspace-volume relative-path guard; the caller is responsible for supplying either `""` or a repository directory produced by Groom's repository selection flow.
- command: runs `docker run --rm -v {volume}:/vol:ro alpine:3.20 find {base} ( -type d ( -name .git -o -name node_modules -o -name __pycache__ -o -name .venv ) -prune ) -o ( -type f -print )`.
- consistency: list-files-result — for `repo_dir="Acme"` contains paths relative to the selected checkout root, never Docker mount paths.
- verify: omits(subject="list_files result for repo_dir Acme", text="/vol/")
- parsing: only stdout lines beginning with `{base}/` are retained, and the returned value drops that prefix so Docker mount paths are never exposed to the dashboard.
- ignored output: blank lines and any `find` stdout line outside the selected base prefix are ignored.
- ordering: returned paths are sorted ascending for a stable tree order.
- pruning: directories named `.git`, `node_modules`, `__pycache__`, and `.venv` are excluded from traversal.
- timeout: the Docker process uses the module default 20-second timeout.
- failure: any non-zero Docker reader process returns an empty list rather than raising to the HTTP handler.
- consistency: list-files-result — is `[]` whenever the Docker process exits with a non-zero return code.
- verify: count(subject="returned file paths after Docker failure", equals=0)
- exceptions: process-launch and timeout exceptions are not converted by this reader; callers that need to recover from those exceptions must do so outside this function.
- side effects: creates only a throwaway read-only Docker container for the read; it does not change files, workflow state, sidecar registry state, or dashboard clients.

## Fields

### field-selected-base-path

- type: absolute path inside the temporary container
- default: `/vol` when `repo_dir == ""`.
- verify: count(subject="returned volume-root-relative file paths", equals=2)
- default: `/vol/{repo_dir}` with a trailing slash stripped from the assembled path when `repo_dir` is non-empty.
- verify: count(subject="returned repo-relative file paths", equals=2)
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
- detail: [workspace volume skip directory names](workspace-volume-skip-directory-names.md)
- meaning: directory basenames pruned from traversal before file output is collected.
- constraints: this is the same skip set exposed by the [Groom Docker I/O module skip dirs field](groom-docker-io-module.md#field-skip-dirs) and keeps fallback file-list data aligned with the sidecar tree reader's vendor and VCS exclusions.

### field-container-image

- type: Docker image reference string
- default: `alpine:3.20`
- required: true
- code: groom/groom/docker_io.py::ALPINE_IMAGE
- detail: [Docker volume helper image](docker-volume-helper-image.md)
- meaning: minimal image used for the throwaway read-only `find` process.
- constraints: the image must provide BusyBox-compatible `find` with `-prune` and `-print` behavior.

### field-command-timeout

- type: `int`
- default: `20`
- required: true
- code: groom/groom/docker_io.py::DOCKER_TIMEOUT
- detail: [Docker command timeout](docker-command-timeout.md)
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

The read resolves the selected base, builds and runs the read-only `find` command, then parses
and sorts accepted output paths. A non-zero Docker process exit produces an empty file list.

Reading proceeds in this order: the selected base resolves to `/vol` when `repo_dir` is empty,
otherwise to `/vol/{repo_dir}` after trimming only trailing slash characters from the assembled
base string; a `find` prune predicate is constructed that matches every skipped directory
basename; one temporary container runs with the workspace volume mounted read-only at `/vol` and
the configured Alpine image as the command image; inside that container, skipped directories are
pruned and every remaining regular file path below the selected base is printed; each stdout line
is stripped of surrounding whitespace; only lines whose stripped text begins with the selected
base plus `/` are kept; the selected-base prefix is removed from each retained line; the retained
relative paths are returned sorted ascending. The obligations this behavior carries — the
selected-root-relative output shape, the empty-list conversion on Docker failure, sort order, and
prefix filtering — are stated as normative claims in [Contract](#contract) and
[list-files](#list-files) above, with their `verify:` checks.

## Failure behavior

- consistency: list-files-result — a successful Docker read that prints no matching regular files under the selected base returns an empty file list.
- verify: count(subject="returned file paths for an empty selected tree", equals=0)
- Unexpected stdout line: ignores a line that is empty after stripping or does not begin with the selected base prefix.
- Missing selected base: represented as the Docker command's non-zero return and converted to `[]`.
- Process launch failure: not converted by this reader; launch exceptions from the subprocess runner propagate to the caller.
- Timeout: not converted by this reader; timeout exceptions from the subprocess runner propagate to the caller.

## Methods

### list-files

- sig: `list_files(volume: str, repo_dir: str = "") -> list[str]`
- abstract: false
- does:
  - Builds the selected base path from `/vol` plus `repo_dir`, preserving the root case as exactly `/vol`.
  - Builds the prune expression from the shared skip directory names `.git`, `node_modules`, `__pycache__`, and `.venv`.
  - Delegates process execution to the [Docker subprocess runner](docker-subprocess-runner.md).
  - Runs one read-only `alpine:3.20` container with `find` to print non-pruned regular files.
  - Converts only matching absolute mount paths into paths relative to the selected base.
  - Sorts the resulting list before returning it.
- raises: propagates process launch exceptions from the [Docker subprocess runner](docker-subprocess-runner.md).
- raises: propagates timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md).
- raises: converts Docker process return-code failures to an empty list.
- returns: sorted list of selected-root-relative file paths.
- verify: count(subject="returned repo-relative file paths", equals=2)
- verify: count(subject="returned volume-root-relative file paths", equals=2)
- returns: an empty list when the selected tree is empty.
- verify: count(subject="returned file paths for an empty selected tree", equals=0)
- returns: an empty list when the Docker process exits non-zero.
- verify: count(subject="returned file paths after Docker failure", equals=0)
- returns: an empty list when no stdout paths match the selected base prefix.
- verify: count(subject="returned file paths with no matching base prefix", equals=0)
- code: groom/groom/docker_io.py::list_files
- detail: [List-files documentation views](list-files-documentation-views.md)
- tests: groom/tests/test_docker_io.py::test_list_files_returns_repo_relative_paths_and_prunes_vendor_dirs,
  groom/tests/test_docker_io.py::test_list_files_volume_root_when_repo_dir_empty,
  groom/tests/test_docker_io.py::test_list_files_empty_on_docker_failure
- args:
  - `volume`: Docker volume name to mount at `/vol` read-only.
  - `repo_dir`: volume-relative checkout directory to list; `""` selects the volume root; callers are responsible for supplying a bounded repository selection because this reader does not apply the relative-path guard.
