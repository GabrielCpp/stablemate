---
type: concept
slug: groom-docker-io-module
title: Groom Docker I/O module
---
# Groom Docker I/O module

Its public helpers present Docker and workspace-volume operations through small return values for callers to interpret.

Groom Docker I/O module is the bounded Docker CLI adapter for the [groom server](../http/groom.md) and [groom sidecar](../groom-sidecar.md) control plane: it centralizes shell-free local Docker subprocess execution, container fleet reads, live container commands, workspace-volume file and diff reads, gate-file writes, and repository discovery. Its public helpers are documented as sibling concepts, including the [Docker subprocess runner](docker-subprocess-runner.md), [Docker all-container listing reader](docker-all-container-listing-reader.md), [Docker container-id listing reader](docker-container-id-listing-reader.md), [Docker exec runner](docker-exec-runner.md), [host-to-container sidecar query](host-to-container-sidecar-query.md), [Docker inspection reader](docker-inspection-reader.md), [stopped container start fallback](stopped-container-start-fallback.md), [container running-state check](container-running-state-check.md), [workspace volume relative-path guard](workspace-volume-relative-path-guard.md), [workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md), [workspace volume file-list reader](workspace-volume-file-list-reader.md), [Docker run-directory reader](docker-run-directory-reader.md), [workspace volume repository-directory reader](workspace-volume-repository-directory-reader.md), [workspace volume diff reader](workspace-volume-diff-reader.md), [workspace volume file-content reader](workspace-volume-file-content-reader.md), and [workspace volume file writer](workspace-volume-file-writer.md). It exchanges [Docker ps container row](../docker-ps-container-row.md), [Docker inspect container object](../docker-inspect-container-object.md), [sidecar snapshot data](../sidecar-snapshot-data.md), [workspace file list data](../workspace-file-list-data.md), [workspace file content data](../workspace-file-content-data.md), and [workspace diff data](../workspace-diff-data.md) without owning workflow registry state, dashboard rendering, sidecar websocket state, or gate-answer orchestration.

- code: groom/groom/docker_io.py
- tests: groom/tests/test_docker_io.py::test_list_container_ids_returns_short_id_set
- tests: groom/tests/test_docker_io.py::test_list_container_ids_returns_none_on_docker_failure
- tests: groom/tests/test_docker_io.py::test_list_container_ids_empty_when_no_containers
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure
- tests: groom/tests/test_docker_io.py::test_git_diff_returns_empty_when_no_repo_found
- tests: groom/tests/test_docker_io.py::test_git_diff_returns_stdout_on_success
- tests: groom/tests/test_docker_io.py::test_git_diff_returns_empty_on_git_failure
- tests: groom/tests/test_docker_io.py::test_grep_awaiting_files_prunes_heavy_dirs_and_parses_paths
- tests: groom/tests/test_docker_io.py::test_grep_awaiting_files_empty_on_docker_failure
- tests: groom/tests/test_docker_io.py::test_list_files_returns_repo_relative_paths_and_prunes_vendor_dirs
- tests: groom/tests/test_docker_io.py::test_list_files_volume_root_when_repo_dir_empty
- tests: groom/tests/test_docker_io.py::test_list_files_empty_on_docker_failure
- tests: groom/tests/test_docker_io.py::test_docker_exec_builds_user_and_env_flags
- tests: groom/tests/test_docker_io.py::test_sidecar_query_parses_snapshot_json
- tests: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_nonzero_exit
- tests: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_non_json_output
- tests: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_when_docker_missing
- tests: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_timeout
- refs: [groom server](../http/groom.md), [groom sidecar](../groom-sidecar.md), [Docker subprocess runner](docker-subprocess-runner.md), [Docker all-container listing reader](docker-all-container-listing-reader.md), [Docker container-id listing reader](docker-container-id-listing-reader.md), [Docker exec runner](docker-exec-runner.md), [host-to-container sidecar query](host-to-container-sidecar-query.md), [Docker inspection reader](docker-inspection-reader.md), [stopped container start fallback](stopped-container-start-fallback.md), [container running-state check](container-running-state-check.md), [workspace volume relative-path guard](workspace-volume-relative-path-guard.md), [workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md), [workspace volume file-list reader](workspace-volume-file-list-reader.md), [Docker run-directory reader](docker-run-directory-reader.md), [workspace volume repository-directory reader](workspace-volume-repository-directory-reader.md), [workspace volume diff reader](workspace-volume-diff-reader.md), [workspace volume file-content reader](workspace-volume-file-content-reader.md), [workspace volume file writer](workspace-volume-file-writer.md)

## Contract

- public surface: the module exposes three Docker image/timeout constants and sixteen public helpers: [docker-ps-all](#docker-ps-all), [list-container-ids](#list-container-ids), [docker-exec](#docker-exec), [sidecar-query](#sidecar-query), [docker-inspect](#docker-inspect), [docker-start](#docker-start), [is-running](#is-running), [safe-relpath](#safe-relpath), [grep-awaiting-files](#grep-awaiting-files), [list-files](#list-files), [list-run-dirs](#list-run-dirs), [list-repo-dirs](#list-repo-dirs), [find-repo-dir](#find-repo-dir), [git-diff](#git-diff), [read-file](#read-file), and [write-file](#write-file).
- execution invariant: every Docker process is launched from an argv list through the [Docker subprocess runner](docker-subprocess-runner.md), not through a shell command string.
- timeout invariant: Docker calls default to [field-docker-timeout](#field-docker-timeout) unless a helper accepts and forwards an explicit timeout.
- image invariant: read-only BusyBox-style volume operations use [field-alpine-image](#field-alpine-image); read-only git diff extraction uses [field-git-image](#field-git-image).
- read boundary: container listings, inspect objects, volume file lists, repository directories, run directories, file contents, and diffs are returned as plain Python values for callers to interpret.
- write boundary: only [write-file](#write-file) writes a workspace volume, and it writes exactly one caller-selected safe relative path from stdin through a temporary container.
- path-safety boundary: helpers that accept file paths inside a volume call [safe-relpath](#safe-relpath) before constructing `/vol/...`; helpers that accept Docker-derived volume names, container ids, or repository directories assume those values have already been bounded by upstream Docker metadata or UI selection.
- failure model: Docker process non-zero exits are converted per helper into `[]`, `set()`, `None`, `False`, or `""` as documented by each method; process launch and timeout exceptions generally propagate except for [sidecar-query](#sidecar-query), which treats expected Docker/subprocess failures as sidecar-unavailable.
- JSON failure model: malformed Docker JSON listing rows are skipped by [docker-ps-all](#docker-ps-all); invalid inspect JSON and invalid sidecar JSON make [docker-inspect](#docker-inspect) and [sidecar-query](#sidecar-query) return `None`.
- state ownership: the module stores no workflow containers, gate records, sidecar sessions, client queues, answer logs, or dashboard state.
- external boundary: the standard library JSON and subprocess runtimes, the local Docker CLI, Docker images, Docker daemon, and mounted volumes are below this module; they are not Groom concepts to descend into.

## Public Helper Matrix

Container fleet reads include [docker-ps-all](#docker-ps-all), which returns parsed all-container rows, and [list-container-ids](#list-container-ids), which returns short ids or Docker-unavailable `None`.

- live container operations: [docker-exec](#docker-exec) runs a caller-selected command in a live container; [sidecar-query](#sidecar-query) uses that exec path to request sidecar state; [docker-inspect](#docker-inspect) reads one inspect object; [docker-start](#docker-start) starts one existing container; [is-running](#is-running) derives a boolean from inspect state.
- workspace path validation: [safe-relpath](#safe-relpath) is the only exported validator for caller-selected workspace-relative file paths.
- workspace-volume reads: [grep-awaiting-files](#grep-awaiting-files) finds awaiting gate files; [list-files](#list-files) lists repo-relative files; [list-run-dirs](#list-run-dirs) lists run directories; [list-repo-dirs](#list-repo-dirs) lists git checkout roots; [find-repo-dir](#find-repo-dir) selects the first checkout root; [git-diff](#git-diff) returns one checkout diff; [read-file](#read-file) returns file text.
- workspace-volume write: [write-file](#write-file) writes one safe relative file path by streaming the new content through stdin.

## Argument Ownership

- container_id: caller-owned string that is passed to Docker commands unchanged by [docker-exec](#docker-exec), [sidecar-query](#sidecar-query), [docker-inspect](#docker-inspect), [docker-start](#docker-start), and [is-running](#is-running); this module does not prove Groom ownership before use.
- args: caller-owned argv suffix for [docker-exec](#docker-exec); each item is appended as an argv token after the target container id.
- user: optional Docker exec user string for [docker-exec](#docker-exec); omitted when falsey and otherwise emitted as `-u <user>`.
- env: optional string mapping for [docker-exec](#docker-exec); each key-value pair is emitted as one `-e KEY=VALUE` argv pair in mapping iteration order.
- timeout: optional seconds integer for [docker-exec](#docker-exec); forwarded to the Docker subprocess runner instead of [field-docker-timeout](#field-docker-timeout).
- volume: Docker volume name used by workspace read/write helpers as the left side of a Docker `-v` mount; it is not path-normalized by this module.
- mount_subdir: optional volume-relative subdirectory for [grep-awaiting-files](#grep-awaiting-files); when empty the search target is `/vol`, otherwise `/vol/<mount_subdir>` with trailing slash removed.
- repo_dir: optional volume-relative repository root for [list-files](#list-files) and [git-diff](#git-diff); empty means volume root for file listing and first discovered repository for diff extraction.
- rel_path: caller-selected workspace-relative path for [read-file](#read-file) and [write-file](#write-file).
- consistency: [read-file](#read-file) and [write-file](#write-file) accept a caller-selected `rel_path` only after [safe-relpath](#safe-relpath) accepts it, so an unsafe path never reaches a Docker argv.
- verify: omits(subject="Docker argv for read-file and write-file with unsafe relative-path inputs", matches="/vol/.*\\.\\./")
- content: text payload for [write-file](#write-file); passed as subprocess stdin and never as a command-line token.

## Return Conventions

- consistency: Docker discovery and volume-scan helpers return sorted or parsed lists and use `[]` for Docker command failure, no matches, or no applicable entries as documented by each method.
- verify: count(subject="Docker discovery and volume-scan result after Docker failure or no matches", equals=0)
- set result: [list-container-ids](#list-container-ids) returns `set()` for a successful no-container listing and `None` only when Docker cannot provide the listing.
- optional dictionary result: [sidecar-query](#sidecar-query) and [docker-inspect](#docker-inspect) return dictionaries only for parseable object payloads; all expected unavailable or invalid states return `None`.
- boolean result: [docker-start](#docker-start) and [write-file](#write-file) return `True` only for completed zero-status Docker processes; [is-running](#is-running) returns `True` only for truthy inspect `State.Running`.
- optional string result: [read-file](#read-file) returns stdout text or `None`; [find-repo-dir](#find-repo-dir) and [git-diff](#git-diff) return `""` when their source repository or diff is unavailable.
- process result: [docker-exec](#docker-exec) returns the raw completed Docker exec process so the caller can decide how to interpret stdout, stderr, and return code.

## Fields

### field-docker-timeout

- type: `int`
- default: `20`
- required: true
- code: groom/groom/docker_io.py::DOCKER_TIMEOUT
- detail: [Docker command timeout](docker-command-timeout.md)
- meaning: default maximum seconds a Docker subprocess may run before the subprocess runtime raises a timeout exception.
- used-by: every helper that calls the [Docker subprocess runner](docker-subprocess-runner.md) without an explicit timeout override.

### field-alpine-image

- type: Docker image reference string
- default: `alpine:3.20`
- required: true
- code: groom/groom/docker_io.py::ALPINE_IMAGE
- detail: [Docker volume helper image](docker-volume-helper-image.md)
- meaning: image used for read-only volume scans, file reads, and file writes that need BusyBox `find`, `grep`, `cat`, or `cp` behavior.
- used-by: [workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md), [workspace volume file-list reader](workspace-volume-file-list-reader.md), [Docker run-directory reader](docker-run-directory-reader.md), [workspace volume repository-directory reader](workspace-volume-repository-directory-reader.md), [workspace volume file-content reader](workspace-volume-file-content-reader.md), and [workspace volume file writer](workspace-volume-file-writer.md).

### field-git-image

- type: Docker image reference string
- default: `alpine/git:2.43.0`
- required: true
- code: groom/groom/docker_io.py::GIT_IMAGE
- meaning: image used for read-only workspace diff extraction.
- used-by: [workspace volume diff reader](workspace-volume-diff-reader.md).

## Methods

### docker-ps-all

- sig: `docker_ps_all() -> list[dict[str, Any]]`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- verify: json_path(path="exception.type", matches="FileNotFoundError|TimeoutExpired")
- returns: parseable rows from Docker's all-container JSON-line listing, or `[]` when Docker reports the listing command failed.
- verify: count(subject="parseable rows from a successful Docker all-container JSON-line listing", equals=2)
- code: groom/groom/docker_io.py::docker_ps_all
- detail: [Docker all-container listing reader](docker-all-container-listing-reader.md)

### list-container-ids

- sig: `list_container_ids() -> set[str] | None`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- returns: a set of twelve-character container id prefixes, an empty set when Docker reports no containers, or `None` when Docker cannot supply the listing.
- verify: count(subject="twelve-character container ID prefixes from a successful listing", equals=2)
- verify: absent(subject="container ID set when Docker listing fails")
- verify: count(subject="container ID prefixes from a successful empty listing", equals=0)
- code: groom/groom/docker_io.py::list_container_ids
- detail: [Docker container-id listing reader](docker-container-id-listing-reader.md)
- detail: [Docker container-id listing documentation scope](docker-container-id-listing-documentation-scope.md)
- tests: groom/tests/test_docker_io.py::test_list_container_ids_returns_short_id_set
- tests: groom/tests/test_docker_io.py::test_list_container_ids_returns_none_on_docker_failure
- tests: groom/tests/test_docker_io.py::test_list_container_ids_empty_when_no_containers

### docker-exec

- sig: `docker_exec(container_id: str, args: list[str], *, user: str | None = None, env: dict[str, str] | None = None, timeout: int = DOCKER_TIMEOUT) -> subprocess.CompletedProcess`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- returns: the completed `docker exec` process result for caller-specific interpretation.
- verify: exit_status(code=0)
- code: groom/groom/docker_io.py::docker_exec
- detail: [Docker exec runner](docker-exec-runner.md)
- detail: [Docker exec documentation scope](docker-exec-documentation-scope.md)
- tests: groom/tests/test_docker_io.py::test_docker_exec_builds_user_and_env_flags

### sidecar-query

- sig: `sidecar_query(container_id: str) -> dict[str, Any] | None`
- abstract: false
- raises: no intentional exception for expected Docker missing, timeout, non-zero exit, non-JSON output, or non-dictionary JSON output.
- raises: unexpected non-subprocess failures can propagate.
- returns: parsed [sidecar snapshot data](../sidecar-snapshot-data.md) dictionary from `groom-sidecar --query`, or `None` when the live sidecar query path is unavailable.
- verify: json_path(path="$.current_node", equals="n1")
- verify: absent(subject="sidecar snapshot data after a non-zero sidecar query exit")
- verify: absent(subject="sidecar snapshot data after non-JSON sidecar query output")
- verify: absent(subject="sidecar snapshot data when Docker is unavailable")
- verify: absent(subject="sidecar snapshot data after a sidecar query timeout")
- code: groom/groom/docker_io.py::sidecar_query
- detail: [host-to-container sidecar query](host-to-container-sidecar-query.md)
- tests: groom/tests/test_docker_io.py::test_sidecar_query_parses_snapshot_json
- tests: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_nonzero_exit
- tests: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_non_json_output
- tests: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_when_docker_missing
- tests: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_timeout

### docker-inspect

- sig: `docker_inspect(container_id: str) -> dict[str, Any] | None`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- verify: json_path(path="exception.type", matches="^(OSError|TimeoutExpired)$")
- returns: the first parsed [Docker inspect container object](../docker-inspect-container-object.md) for a zero-exit, valid-JSON, truthy response.
- verify: json_path(path="result.Id", equals="container-123")
- returns: `None` for Docker failure.
- verify: json_path(path="result", equals=null)
- returns: `None` for invalid JSON.
- verify: json_path(path="result", equals=null)
- returns: `None` for an empty inspect array.
- verify: json_path(path="result", equals=null)
- code: groom/groom/docker_io.py::docker_inspect
- detail: [Docker inspection reader](docker-inspection-reader.md)
- detail: [Docker inspect documentation scope](docker-inspect-documentation-scope.md)

### docker-start

- sig: `docker_start(container_id: str) -> bool`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- verify: json_path(path="exception.type", matches="FileNotFoundError|TimeoutExpired")
- returns: `true` only when `docker start <container_id>` completes with return code `0`.
- verify: json_path(path="return value", equals=true)
- code: groom/groom/docker_io.py::docker_start
- detail: [Docker start documentation scope](docker-start-documentation-scope.md)
- detail: [stopped container start fallback](stopped-container-start-fallback.md)

### is-running

- sig: `is_running(container_id: str) -> bool`
- abstract: false
- raises: subprocess launch and timeout exceptions from [docker-inspect](#docker-inspect) can propagate.
- verify: json_path(path="exception.type", matches="^(OSError|TimeoutExpired)$")
- returns: `true` only when inspect data exists and `State.Running` is truthy.
- verify: json_path(path="result", equals=true)
- code: groom/groom/docker_io.py::is_running
- detail: [container running-state check](container-running-state-check.md)

### safe-relpath

- sig: `safe_relpath(path: str) -> str`
- abstract: false
- raises: `ValueError` when the supplied path is empty, absolute, contains backslash-root syntax, contains an empty segment, or contains `..`.
- verify: json_path(path="exception.type", equals="ValueError")
- returns: the path normalized to forward-slash separators without changing segment names.
- verify: json_path(path="result", equals="a/b/c")
- code: groom/groom/docker_io.py::safe_relpath
- detail: [workspace volume relative-path guard](workspace-volume-relative-path-guard.md)
- detail: [safe relpath documentation views](safe-relpath-documentation-views.md)

### grep-awaiting-files

- sig: `grep_awaiting_files(volume: str, mount_subdir: str = "") -> list[str]`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- returns: workspace-volume-relative paths for files that contain an awaiting [operator gate context file](../operator-gate-context-file.md) status line, or `[]` for Docker failure or no matches.
- verify: count(subject="awaiting file paths after a successful sweep", equals=2)
- verify: count(subject="awaiting file paths after Docker failure", equals=0)
- code: groom/groom/docker_io.py::grep_awaiting_files
- detail: [Grep awaiting-files documentation views](grep-awaiting-files-documentation-views.md)
- detail: [workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md)
- tests: groom/tests/test_docker_io.py::test_grep_awaiting_files_prunes_heavy_dirs_and_parses_paths
- tests: groom/tests/test_docker_io.py::test_grep_awaiting_files_empty_on_docker_failure

### list-files

- sig: `list_files(volume: str, repo_dir: str = "") -> list[str]`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- returns: sorted repo-relative [workspace file list data](../workspace-file-list-data.md), or `[]` for Docker failure or an empty tree.
- code: groom/groom/docker_io.py::list_files
- detail: [List-files documentation views](list-files-documentation-views.md)
- detail: [workspace volume file-list reader](workspace-volume-file-list-reader.md)
- tests: groom/tests/test_docker_io.py::test_list_files_returns_repo_relative_paths_and_prunes_vendor_dirs
- tests: groom/tests/test_docker_io.py::test_list_files_volume_root_when_repo_dir_empty
- tests: groom/tests/test_docker_io.py::test_list_files_empty_on_docker_failure

### list-run-dirs

- sig: `list_run_dirs(volume: str) -> list[str]`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- verify: json_path(path="exception.type", matches="^(FileNotFoundError|TimeoutExpired)$")
- returns: sorted top-level directory names under a `/runs` volume.
- verify: json_path(path="result", equals=["older-run", "newer-run"])
- returns: `[]` for Docker failure.
- verify: json_path(path="result", equals=[])
- code: groom/groom/docker_io.py::list_run_dirs
- detail: [Docker run-directory reader](docker-run-directory-reader.md)
- detail: [Docker run-directory listing documentation views](docker-run-directory-listing-documentation-views.md)

### list-repo-dirs

- sig: `list_repo_dirs(volume: str) -> list[str]`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- returns: sorted volume-relative paths to git checkout roots discovered within two levels of the volume root, or `[]` for Docker failure or no repositories.
- verify: count(subject="repository directories discovered from /vol/Acme/.git", equals=1)
- verify: count(subject="repository directories discovered from a volume with no .git directory", equals=0)
- verify: count(subject="repository directories after Docker failure", equals=0)
- code: groom/groom/docker_io.py::list_repo_dirs
- detail: [workspace volume repository-directory reader](workspace-volume-repository-directory-reader.md)
- detail: [Repository-directory listing documentation scope](repository-directory-listing-documentation-scope.md)
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure

### find-repo-dir

- sig: `find_repo_dir(volume: str) -> str`
- abstract: false
- raises: subprocess launch and timeout exceptions from [list-repo-dirs](#list-repo-dirs) can propagate.
- returns: the first sorted repository directory from [list-repo-dirs](#list-repo-dirs), or `""` when none exists.
- code: groom/groom/docker_io.py::find_repo_dir
- detail: [first-repository lookup](workspace-volume-repository-directory-reader.md#find-repo-dir)
- detail: [Repository-directory lookup documentation scope](repository-directory-lookup-documentation-scope.md)
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure

### git-diff

- sig: `git_diff(volume: str, repo_dir: str = "") -> str`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- returns: raw [workspace diff data](../workspace-diff-data.md) from `git diff HEAD`, or `""` when no repository is available or the git process fails.
- verify: count(subject="diff output bytes when no repository is found", equals=0)
- verify: count(subject="diff output bytes for a successful git diff", equals=31)
- verify: count(subject="diff output bytes when git exits non-zero", equals=0)
- code: groom/groom/docker_io.py::git_diff
- detail: [workspace volume diff reader](workspace-volume-diff-reader.md)
- detail: [Docker git diff documentation scope](docker-git-diff-documentation-scope.md)
- tests: groom/tests/test_docker_io.py::test_git_diff_returns_empty_when_no_repo_found
- tests: groom/tests/test_docker_io.py::test_git_diff_returns_stdout_on_success
- tests: groom/tests/test_docker_io.py::test_git_diff_returns_empty_on_git_failure

### read-file

- sig: `read_file(volume: str, rel_path: str) -> str | None`
- abstract: false
- raises: `ValueError` from [safe-relpath](#safe-relpath).
- verify: json_path(path="exception.type", equals="ValueError")
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- verify: json_path(path="exception.type", matches="FileNotFoundError|TimeoutExpired")
- returns: text [workspace file content data](../workspace-file-content-data.md), or `None` when Docker cannot read the selected safe path.
- verify: json_path(path="result", equals="print(1)\n")
- verify: json_path(path="result", equals=null)
- code: groom/groom/docker_io.py::read_file
- detail: [workspace volume file-content reader](workspace-volume-file-content-reader.md)
- detail: [read-file documentation scope](read-file-documentation-scope.md)

### write-file

- sig: `write_file(volume: str, rel_path: str, content: str) -> bool`
- abstract: false
- raises: `ValueError` from [safe-relpath](#safe-relpath).
- verify: absent(subject="Docker subprocess invocation for an unsafe relative path")
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate.
- verify: json_path(path="exception.type", matches="FileNotFoundError|TimeoutExpired")
- returns: `true` only when the temporary container copies the supplied content to the selected safe path with return code `0`.
- verify: json_path(path="result", equals=true)
- code: groom/groom/docker_io.py::write_file
- detail: [workspace volume file writer](workspace-volume-file-writer.md)

## Folded Internal Members

### method: run

- sig: `_run(args: list[str], timeout: int = DOCKER_TIMEOUT, input_text: str | None = None) -> subprocess.CompletedProcess`
- abstract: false
- raises: process launch and timeout exceptions from the subprocess runtime.
- verify: json_path(path="exception.type", matches="^(FileNotFoundError|TimeoutExpired)$")
- code: groom/groom/docker_io.py::_run
- detail: [Docker subprocess runner documentation](docker-subprocess-runner-documentation.md)

### field: skip dirs

- type: `tuple[str, ...]`
- default: `(".git", "node_modules", "__pycache__", ".venv")`
- required: true
- code: groom/groom/docker_io.py::_SKIP_DIRS
- detail: [workspace volume skip directory names](workspace-volume-skip-directory-names.md)

## Algorithms

### algorithm-docker-read-and-write-boundary

Each helper converts its completed process and stdout into that method's documented return value;
workflow-state mutation, UI rendering, websocket sending, and gate-answer decisions remain with
the caller.

- step: A caller selects a public helper for a container listing, container inspection, live exec, sidecar query, volume scan, repository discovery, file read, diff read, or file write.
- step: The helper validates only the path inputs it owns, using [safe-relpath](#safe-relpath) for volume file paths that would otherwise become `/vol/...` destinations.
- step: The helper builds a tokenized Docker argv list using [field-alpine-image](#field-alpine-image), [field-git-image](#field-git-image), or the host Docker CLI command needed for the requested operation.
- step: The helper delegates process launch and output capture to the [Docker subprocess runner](docker-subprocess-runner.md).

### algorithm-helper-call-graph

- step: [sidecar-query](#sidecar-query) calls [docker-exec](#docker-exec) with the fixed sidecar query argv, user `nobody`, and HOME override, then parses stdout as JSON.
- step: [is-running](#is-running) calls [docker-inspect](#docker-inspect) and reads only `State.Running` from the returned inspect object.
- step: [find-repo-dir](#find-repo-dir) calls [list-repo-dirs](#list-repo-dirs) and selects the first sorted entry when present.
- step: [git-diff](#git-diff) calls [find-repo-dir](#find-repo-dir) only when no repository directory is supplied by the caller.
- step: [read-file](#read-file) and [write-file](#write-file) call [safe-relpath](#safe-relpath) before constructing the mounted destination path.
- step: All other public helpers call only the folded [Docker subprocess runner](docker-subprocess-runner.md#run), standard JSON parsing where needed, and external Docker processes.

## Failure Behavior

- consistency: Docker CLI non-zero exits are converted by each public helper into its documented empty, false, or unavailable return value unless the helper intentionally returns the raw completed process.
- Docker CLI missing or timeout: propagates from most helpers, but [sidecar-query](#sidecar-query) catches expected operating-system and subprocess failures and returns `None` so discovery can fall back to volume reads.
- Malformed JSON: ignored per line by [docker-ps-all](#docker-ps-all), converted to `None` by [docker-inspect](#docker-inspect), and converted to `None` by [sidecar-query](#sidecar-query).
- Unsafe relative file path: [safe-relpath](#safe-relpath), [read-file](#read-file), and [write-file](#write-file) raise `ValueError` before Docker receives the path.
- Missing repository: [find-repo-dir](#find-repo-dir) and [git-diff](#git-diff) return empty strings rather than raising a Groom-domain error.
