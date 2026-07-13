---
type: concept
slug: workspace-volume-awaiting-file-reader
title: Workspace-volume awaiting-file reader
---
# Workspace-volume awaiting-file reader

Workspace-volume awaiting-file reader is the Docker-volume sweep used by the [workflow discovery scan](workflow-discovery-scan.md#method-find-awaiting-gates) when the sidecar query path is unavailable and Groom must recover open gates from a workflow container's `/workspace` volume. It uses the [Docker subprocess runner](docker-subprocess-runner.md) to start one throwaway read-only Alpine container, searches for files whose status line contains the [operator gate context file](../operator-gate-context-file.md) awaiting token, prunes heavy vendor and VCS directories, and returns workspace-volume-relative candidate paths for the discovery layer to reread before creating [gate info](gate-info.md) records.

- code: groom/groom/docker_io.py::grep_awaiting_files
- verify: groom/tests/test_docker_io.py::test_grep_awaiting_files_prunes_heavy_dirs_and_parses_paths
- verify: groom/tests/test_docker_io.py::test_grep_awaiting_files_empty_on_docker_failure
- refs: [workflow discovery scan](workflow-discovery-scan.md#method-find-awaiting-gates), [Docker subprocess runner](docker-subprocess-runner.md), [operator gate context file](../operator-gate-context-file.md), [gate info](gate-info.md)

## Contract

- purpose: find candidate operator gate context files in a Docker named workspace volume during best-effort discovery fallback.
- input: `volume` is the Docker named volume mounted at `/workspace` for an eligible workflow container, passed directly to Docker as the source side of a read-only volume mount.
- input: `mount_subdir` is an optional volume-relative subdirectory to scan; the default `""` scans the volume root and Groom's discovery fallback currently supplies the default.
- target path: the read-only container scans `/vol/<mount_subdir>` with trailing slashes removed, or `/vol` when the normalized target would otherwise be empty.
- mount-subdir normalization: no leading-slash, `..`, empty-segment, or shell validation is applied to `mount_subdir`; the reader only prefixes it with `/vol/` and strips trailing slashes before handing the target to Docker.
- search rule: retained files are regular files whose full contents include a line beginning with `STATUS:`, followed by zero or more POSIX whitespace characters, followed by `AWAITING_OPERATOR`.
- skip rule: directories named `.git`, `node_modules`, `__pycache__`, or `.venv` are pruned before file matching so repository metadata, dependency trees, bytecode caches, and local virtual environments are not traversed.
- output: `list[str]` containing each matching path made relative to `/vol/`, preserving the Docker command's output order.
- ordering rule: preserves observed Docker stdout order and performs no sorting or deduplication.
- empty result: returns `[]` when Docker reports no matching files, when Docker command execution fails, or when the command output contains no `/vol/`-prefixed paths.
- process boundary: invokes Docker without a shell and mounts the target volume read-only at `/vol` inside the temporary container.
- candidate boundary: proves only that the file matched the cheap status-line search at sweep time; it does not prove the file is still awaiting when a gate record is created.
- trust boundary: does not validate or sanitize `volume` or `mount_subdir`; callers provide these values from Docker mount metadata or other already-bounded internal discovery state, and callers that reread returned paths own path safety for that later read.
- persistence: does not write the workspace volume, answer gates, update workflow state, mutate the registry, broadcast UI fragments, or start or stop workflow containers.

## Fields

### field-skipped-directory-names

- type: `tuple[str, ...]`
- default: `(".git", "node_modules", "__pycache__", ".venv")`
- required: true
- code: groom/groom/docker_io.py::_SKIP_DIRS
- meaning: directory basenames pruned from the awaiting-file sweep before matching files.
- constraints: the same skip set is intended to mirror the sidecar snapshot sweep so host fallback discovery and in-container sidecar discovery ignore the same heavy or non-domain directories.

### field-search-status-pattern

- type: POSIX extended regular expression string
- default: literal `^STATUS:`, then a zero-or-more POSIX whitespace character class, then literal `AWAITING_OPERATOR`.
- required: true
- code: groom/groom/docker_io.py::grep_awaiting_files
- meaning: line-level content pattern that marks a file as a candidate awaiting operator gate context file.
- constraints: this is only a candidate filter; the discovery layer rereads each returned file and applies the shared status parser before a gate becomes actionable.

### field-container-image

- type: Docker image reference string
- default: `alpine:3.20`
- required: true
- code: groom/groom/docker_io.py::ALPINE_IMAGE
- meaning: minimal image used for the throwaway read-only `find` and `grep` process.
- constraints: the image must provide BusyBox-compatible `find` with `-prune` and `-exec ... +` support and `grep -lE`.

### field-command-timeout

- type: `int`
- default: `20`
- required: true
- code: groom/groom/docker_io.py::DOCKER_TIMEOUT
- meaning: maximum seconds allowed for the Docker command unless the shared runner's default changes.
- constraints: a timeout exception from the subprocess layer is not converted by this reader.

## Effects

- Builds: a target path under `/vol` from the optional mount subdirectory without adding shell quoting or command-string interpolation.
- Builds: a `find` prune expression from the skipped directory names, joining multiple directory-name tests with `-o`.
- Builds: a fixed argv vector whose search portion prunes skipped directory names, visits regular files only, and runs `grep -lE` with the awaiting-status pattern against each batched file set.
- Calls: the [Docker subprocess runner](docker-subprocess-runner.md) once with a tokenized `docker run --rm -v <volume>:/vol:ro alpine:3.20 find <target> ... grep -lE <awaiting-status-pattern> ...` argv list.
- Treats: Docker return code `0` as successful matches and return code `1` as a successful no-match sweep.
- Converts: any other Docker return code to `[]` because fallback gate recovery is best-effort.
- Parses: stdout line by line, stripping surrounding whitespace from each line.
- Emits: only lines beginning with `/vol/`, with that prefix removed so callers receive workspace-volume-relative file paths.
- Ignores: matching stdout lines that are not under `/vol/`, including Docker noise, warnings, or malformed tool output.
- Preserves: candidate file content, non-candidate files, skipped directory contents, Docker volumes, workflow containers, registry state, sidecar sessions, and dashboard clients.

## Algorithms

### algorithm-awaiting-file-sweep

- step: Normalize the scan target to `/vol/<mount_subdir>` without a trailing slash, falling back to `/vol` when the subdirectory is empty.
- step: Construct a `find` prune predicate that matches every skipped directory basename.
- step: Run one read-only temporary container with the workspace volume mounted at `/vol`.
- step: In that container, prune skipped directories and pass every remaining regular file to `grep -lE` with the awaiting-status pattern.
- step: If the Docker process exits with a code other than `0` or `1`, return an empty list.
- step: For each stdout line, strip whitespace and keep only `/vol/`-prefixed paths.
- step: Remove the `/vol/` prefix from each retained path.
- step: Return the retained relative paths in observed order.

## Failure behavior

- Docker command failure: returns `[]` for non-`0`/`1` process return codes.
- No awaiting files: returns `[]` when grep reports no matches with return code `1`.
- Unexpected stdout line: ignores a line that is empty after stripping or does not begin with `/vol/`.
- Process launch failure: not converted by this reader; launch exceptions from the subprocess runner propagate to the caller.
- Timeout: not converted by this reader; timeout exceptions from the subprocess runner propagate to the caller.

## Methods

### method-grep-awaiting-files

- sig: `grep_awaiting_files(volume: str, mount_subdir: str = "") -> list[str]`
- abstract: false
- raises: propagates process launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md); converts Docker process return-code failures to an empty list.
- returns: workspace-volume-relative candidate file paths in observed command-output order, with no sorting, deduplication, status parser validation, or question extraction.
- code: groom/groom/docker_io.py::grep_awaiting_files
- verify: groom/tests/test_docker_io.py::test_grep_awaiting_files_prunes_heavy_dirs_and_parses_paths
- verify: groom/tests/test_docker_io.py::test_grep_awaiting_files_empty_on_docker_failure

Returns the workspace-volume-relative paths of files that appear to carry an awaiting operator status line. The method is intentionally a candidate producer: it does not parse gate context, extract questions, verify the file is still awaiting after the sweep, or create gate records.

#### Contract

- input: accepts one Docker volume name and an optional volume-relative subdirectory string.
- output: returns candidate paths relative to the mounted volume root, including the subdirectory prefix when the scan target is below the root.
- caller contract: callers that need a live gate must reread each candidate and apply the shared [operator gate context file](../operator-gate-context-file.md) parser before creating state.

#### Effects

- Delegates: all process execution to the [Docker subprocess runner](docker-subprocess-runner.md).
- Builds command: mounts the supplied volume at `/vol:ro`, runs the configured Alpine image, prunes skipped directories with `find`, and invokes `grep -lE` against regular files only.
- Scans: regular files reachable from the normalized target path after skip-directory pruning.
- Filters: returns only Docker stdout lines whose stripped text starts with `/vol/`.
- Preserves order: appends each retained stdout line to the returned list in the order emitted by the command.

#### Failure behavior

- Docker no-match return: returns `[]` for return code `1`.
- Docker failure return: returns `[]` for any return code other than `0` or `1`.
- Malformed stdout: ignores non-`/vol/` output lines without failing the sweep.
