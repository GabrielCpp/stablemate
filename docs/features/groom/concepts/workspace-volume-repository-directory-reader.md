---
type: concept
slug: workspace-volume-repository-directory-reader
title: Workspace volume repository-directory reader
---
# Workspace volume repository-directory reader

Workspace volume repository-directory reader is the fallback checkout discovery used by the [serve repository menu](../http/groom.md#serve-repository-menu) invocation to produce [repository menu data](../repository-menu-data.md) and by the [workspace volume diff reader](workspace-volume-diff-reader.md) when a diff request does not name a checkout. It reads a known workflow workspace Docker volume through the shared [Docker subprocess runner](docker-subprocess-runner.md), discovers git checkout directories near the volume root, returns volume-relative repository paths for dashboard repository selection, and can collapse that ordered list to the first checkout for single-repository callers without mutating the workspace, workflow state, sidecar registry, or dashboard clients.

- code: groom/groom/docker_io.py::list_repo_dirs
- verify: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure,
  groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo

## Contract

- purpose: provide repository-picker checkout discovery for workflows whose workspace volume is known.
- input: `volume` is the Docker workspace volume name mounted read-only at `/vol` for the duration of discovery.
- output: returns `list[str]` containing volume-relative parent directories for every `.git` directory found one or two directory levels below the volume root.
- output: returns `[]` when the Docker discovery process exits non-zero or when no matching `.git` directories are found.
- output: the single-repository lookup returns the first sorted checkout directory, or `""` when the discovery result is empty.
- validation: this reader does not sanitize or normalize the Docker volume name; first-party callers supply the workspace-volume value from workflow discovery or workflow state.
- ordering: returned checkout directories are sorted ascending for stable repository-menu option order.
- ordering: the single-repository lookup therefore chooses the lexicographically first discovered checkout.
- search scope: only directories named `.git` with type directory and depth `/vol/*/.git` or `/vol/*/*/.git` are considered; deeper nested checkouts and non-directory `.git` files are ignored.
- path normalization: each accepted output line must start with `/vol/` and end with `/.git`; the returned value strips those sentinels and preserves the intervening relative directory text unchanged.
- ignored output: blank lines, whitespace-only lines, and non-matching stdout lines are skipped rather than treated as errors.
- command: runs a throwaway `alpine:3.20` container with the workspace volume mounted read-only at `/vol` and executes `find /vol -mindepth 1 -maxdepth 2 -name .git -type d`.
- timeout behavior: the Docker command uses the shared Docker I/O timeout of 20 seconds; timeout or process-launch exceptions are not converted into an empty repository list by this reader.
- command execution: delegates process launch, text stdout/stderr capture, timeout enforcement, and return-code capture to the [Docker subprocess runner](docker-subprocess-runner.md).
- side effects: creates only a throwaway read-only Docker container for discovery; it does not change files, workflow state, sidecar registry state, or dashboard clients.

## Methods

### list-repo-dirs

- sig: `list_repo_dirs(volume: str) -> list[str]`
- abstract: Discover git checkout roots inside a workspace volume and return the volume-relative directories consumed by [repository menu data](../repository-menu-data.md).
- raises: none intentionally surfaced to callers for Docker non-zero exit; process-launch and timeout exceptions from the subprocess runner are not converted by this function.
- returns: sorted volume-relative checkout directories, or `[]` for Docker non-zero completion, no matching checkout directories, or no accepted stdout lines.
- code: groom/groom/docker_io.py::list_repo_dirs
- verify: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git
- verify: groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found
- verify: groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure
- verify: groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo
- volume: required Docker workspace volume name; mounted read-only at `/vol` for the throwaway discovery container.
- calls: [Docker subprocess runner](docker-subprocess-runner.md#run) for the throwaway `find` command.
- effects: creates a read-only temporary Docker container to inspect directory names; performs no file writes, no dashboard broadcast, no sidecar RPC, and no workflow-container restart.
- steps:
  - Build a shell-free Docker command that mounts `volume` read-only at `/vol` in `alpine:3.20` and runs `find /vol -mindepth 1 -maxdepth 2 -name .git -type d`.
  - Run that command through the [Docker subprocess runner](docker-subprocess-runner.md) with the shared Docker timeout.
  - Return `[]` when the process exits non-zero.
  - For each stdout line, trim surrounding whitespace and accept only paths that start with `/vol/` and end with `/.git`.
  - Ignore any trimmed stdout line that is blank, lacks the `/vol/` prefix, or lacks the `/.git` suffix.
  - Convert each accepted path to the repository directory by stripping `/vol/` and `/.git`.
  - Return the accepted repository directories sorted ascending.

### find-repo-dir

- code: groom/groom/docker_io.py::find_repo_dir
- verify: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure
- sig: `find_repo_dir(volume: str) -> str`
- abstract: Select the first available checkout directory for single-repository consumers such as [workspace diff data](../workspace-diff-data.md).
- raises: none intentionally surfaced by this adapter for Docker non-zero exit; it inherits any process-launch or timeout exception not converted by `list_repo_dirs`.
- returns: first sorted volume-relative checkout directory, or `""` when no checkout directory is available.
- volume: required Docker workspace volume name; passed unchanged to [list-repo-dirs](#list-repo-dirs).
- calls: [list-repo-dirs](#list-repo-dirs) to perform all Docker discovery and sorting.
- effects: delegates discovery to [list-repo-dirs](#list-repo-dirs); performs no independent Docker call, file write, dashboard broadcast, sidecar RPC, or workflow-container restart.
- steps:
  - Ask `list_repo_dirs` to discover the sorted checkout directories in `volume`.
  - Return the first discovered directory when at least one checkout exists.
  - Return `""` when discovery yields no checkout directories.
