---
type: concept
slug: docker-run-directory-reader
title: Docker run-directory reader
---
# Docker run-directory reader

Docker run-directory reader, also described by Groom's run-artifact formats as the Docker volume run-directory reader, is the read-only Docker volume helper in the [Groom Docker I/O module](groom-docker-io-module.md) used by the [workflow discovery scan](workflow-discovery-scan.md#method-current-run-state) to choose the latest stopped-or-legacy run directory before reading [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md) and [sidecar run metadata](../sidecar-run-metadata.md). Its [list-run-dirs](#list-run-dirs) method mounts the workflow's runs volume through the shared [Docker subprocess runner](docker-subprocess-runner.md), lists only top-level directories under the volume root, strips the container-local `/vol/` prefix, and returns sorted volume-relative directory names.

- code: groom/groom/docker_io.py::list_run_dirs
- parent: [Groom Docker I/O module](groom-docker-io-module.md)
- alias: Docker volume run-directory reader
- refs: [Docker subprocess runner](docker-subprocess-runner.md), [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md), [sidecar run metadata](../sidecar-run-metadata.md), [workflow discovery scan](workflow-discovery-scan.md#method-current-run-state)
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes

## Contract

- purpose: expose the directory ids currently present at the top level of a workflow `/runs` Docker volume so discovery can select the most recent run without reading every run artifact.
- input: `volume` is a Docker named volume string copied from a discovered workflow container's `/runs` mount metadata.
- input trust: the supplied Docker volume name is passed into the Docker mount argument unchanged; this reader does not validate, normalize, or path-guard Docker volume names because they come from Docker inspect metadata rather than operator input.
- command: invokes `docker run --rm -v <volume>:/vol:ro alpine:3.20 find /vol -mindepth 1 -maxdepth 1 -type d` through the shared subprocess runner with the default Docker timeout, passing each token as a separate process argument.
- mount mode: mounts the supplied volume read-only at `/vol` inside the throwaway container.
- container image: uses the shared Alpine helper image configured for Docker volume readers.
- timeout: uses the shared Docker helper timeout for the whole throwaway container command.
- output: returns `list[str]` containing volume-relative top-level directory names only; directory contents, full absolute container paths, and file entries are never returned.
- path conversion: keeps only stdout lines that start with `/vol/` and removes that prefix from each retained line.
- ordering: sorts the retained directory names lexicographically before returning them; run ids embed sortable timestamps, so callers can use the final item as the newest run when the volume follows Groom's run-id convention.
- validation: does not parse, normalize, deduplicate, shell-expand, or schema-check the retained directory names; any top-level directory name produced by Docker `find` is eligible output after prefix stripping.
- filtering: excludes blank lines, lines outside the `/vol/` prefix, files, symlinks that are not reported as directories by `find -type d`, nested directories below top-level run directories, and any Docker output that is not a matching top-level directory path.
- empty state: returns `[]` when the command succeeds but the volume contains no top-level directories or produces no retained `/vol/` lines.
- failure: returns `[]` when the Docker command exits non-zero, treating an unreadable volume, missing Docker daemon, missing image, or failed `find` command as no usable run directories for discovery fallback.
- failure boundary: process launch failures and subprocess timeout errors from the shared runner are not converted by this layer.
- side effects: performs only a read-only directory listing through a throwaway container; it does not mutate Docker volumes, workflow containers, run artifacts, gate files, registry state, dashboard clients, or sidecar sessions.

## Fields

### field-runs-volume-name

- type: Docker named volume string
- default: none
- required: true
- meaning: name of the workflow container's `/runs` volume to mount read-only for the listing.
- source: Docker inspect mount metadata selected by the workflow discovery scan, not direct operator input.
- constraints: forwarded unchanged into the Docker volume mount argument; this reader does not normalize, quote, shell-expand, schema-check, or path-guard volume names.

### field-mounted-root-path

- type: absolute path inside the temporary container
- default: `/vol`
- required: true
- meaning: container-local root of the mounted runs volume whose direct child directories are eligible output.
- constraints: fixed by this reader; callers cannot select a subdirectory, parent path, or alternate mount target.

### field-container-image

- type: Docker image reference string
- default: `alpine:3.20`
- required: true
- code: groom/groom/docker_io.py::ALPINE_IMAGE
- meaning: minimal image used for the throwaway read-only `find` process.
- constraints: the image must provide `find` with `-mindepth`, `-maxdepth`, and `-type d` behavior for direct child directory discovery.

### field-command-timeout

- type: `int`
- default: `20`
- required: true
- code: groom/groom/docker_io.py::DOCKER_TIMEOUT
- meaning: maximum seconds allowed for the Docker command through the shared runner.
- constraints: a timeout exception from the subprocess layer is not converted by this reader.

### field-returned-run-directory-name

- type: `str`
- default: none
- required: false
- meaning: one retained direct child directory name relative to the runs volume root.
- derivation: remove the exact `/vol/` prefix from one stripped stdout line emitted by the temporary container's `find` command.
- constraints: may contain any name reported by Docker `find` for a direct child directory; this reader does not require a run-id pattern, timestamp segment, uniqueness, or non-empty post-prefix schema beyond the retained `/vol/` stdout prefix.

## Effects

- Calls: the shared [Docker subprocess runner](docker-subprocess-runner.md) once with a tokenized read-only `docker run` command and the default Docker timeout.
- Supplies: the exact argv sequence `docker`, `run`, `--rm`, `-v`, `<volume>:/vol:ro`, `alpine:3.20`, `find`, `/vol`, `-mindepth`, `1`, `-maxdepth`, `1`, `-type`, `d`.
- Reads: the top-level directory entries visible under `/vol` in the mounted runs volume.
- Short-circuits: returns `[]` immediately when the completed Docker process has a non-zero return code.
- Filters: trims each stdout line and keeps only paths that begin with `/vol/`.
- Derives: one volume-relative directory name by removing the `/vol/` prefix from each retained path.
- Emits: the retained names sorted in ascending lexical order, preserving duplicates if duplicated eligible lines appear in stdout.
- Preserves: directory contents, file contents, directory timestamps, Docker containers, mounted volumes, workflow registry entries, and all non-directory run artifacts.

## Algorithms

### algorithm-list-run-directories

- step: Build one tokenized Docker command that mounts the supplied runs volume at `/vol` in read-only mode and runs `find` from the volume root with minimum and maximum depth both constrained to direct children.
- step: Ask the shared Docker subprocess runner to execute the command with the shared Docker timeout.
- step: If the process exits with any non-zero return code, return an empty list.
- step: Split standard output into lines and trim surrounding whitespace from each line.
- step: Retain only lines whose trimmed value begins with `/vol/`.
- step: Remove the `/vol/` prefix from each retained path to make the value relative to the runs volume root.
- step: Sort the retained relative names lexicographically.
- step: Return the sorted list.

## Failure behavior

- Empty volume: a successful command with no matching top-level directories returns `[]`.
- Docker command failure: any non-zero process return code returns `[]`, including missing volume, missing Docker daemon, missing image, and `find` failure cases represented by Docker as a completed failed process.
- Process launch failure: not converted; operating-system launch exceptions from the shared subprocess runner propagate to the caller.
- Timeout failure: not converted; subprocess timeout exceptions from the shared subprocess runner propagate to the caller.
- Unexpected stdout: lines that do not use the `/vol/` prefix are ignored, and retained duplicate lines remain duplicates until the final sorted output.

## Boundaries

- Does not read `checkpoint.json`, `run.json`, gate files, sidecar snapshots, Docker inspect metadata, or Docker container listings.
- Does not decide which returned directory is current; the workflow discovery scan selects the final sorted entry.
- Does not validate run-id syntax or require any specific workflow-id or timestamp pattern in directory names.
- Does not mutate run directories, mounted volumes, workflow container records, the workflow registry, sidecar sessions, dashboard clients, or gate files.

## Methods

### list-run-dirs

- sig: `list_run_dirs(volume: str) -> list[str]`
- abstract: false
- raises: subprocess launch and timeout exceptions from the shared runner are intentionally surfaced rather than mapped to an empty listing.
- returns: sorted list of direct-child run directory names relative to the mounted runs volume root; an empty list means the Docker process exited non-zero, the volume has no retained direct child directories, or stdout produced no retained `/vol/` paths.
- code: groom/groom/docker_io.py::list_run_dirs
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes
- args:
  - `volume`: [field-runs-volume-name](#field-runs-volume-name), required, no default.
- output: zero or more [field-returned-run-directory-name](#field-returned-run-directory-name) values sorted lexicographically.

Returns sorted volume-relative names for the top-level directories in one workflow runs volume, or an empty list when the Docker listing command fails or yields no eligible directory paths.

#### Contract

- input: accepts one Docker volume name string and uses it as the source side of the Docker read-only volume mount.
- command: executes the exact argv sequence `docker`, `run`, `--rm`, `-v`, `<volume>:/vol:ro`, `alpine:3.20`, `find`, `/vol`, `-mindepth`, `1`, `-maxdepth`, `1`, `-type`, `d`.
- output: returns only direct child directory names below the mounted runs-volume root, sorted lexicographically.
- empty output: returns `[]` when Docker succeeds but stdout contains no retained `/vol/` directory paths.
- caller contract: callers that need the current run choose from this returned list; this method does not select, inspect, or validate a run directory.

#### Effects

- Delegates: all process execution, text capture, timeout enforcement, and process-return reporting to the [Docker subprocess runner](docker-subprocess-runner.md).
- Scans: the mounted volume root for direct child directories only.
- Filters: ignores stdout lines that do not begin with `/vol/` after whitespace trimming.

#### Failure behavior

- Docker failure return: returns `[]` for any non-zero process return code.
- Empty stdout: returns `[]` when the successful process emits no retained `/vol/` paths.
- Malformed stdout: ignores non-`/vol/` output lines without failing the listing.
