---
type: concept
slug: workspace-volume-repository-directory-reader
title: Workspace volume repository-directory reader
---
# Workspace volume repository-directory reader

Workspace volume repository-directory reader is the fallback checkout discovery used by the [serve repository menu](../http/groom.md#serve-repository-menu) invocation to produce [repository menu data](../repository-menu-data.md) and by the [workspace volume diff reader](workspace-volume-diff-reader.md) when a diff request does not name a checkout. It reads a known workflow workspace Docker volume through the shared [Docker subprocess runner](docker-subprocess-runner.md), discovers git checkout directories near the volume root, returns volume-relative repository paths for dashboard repository selection, and can collapse that ordered list to the first checkout for single-repository callers without mutating the workspace, workflow state, sidecar registry, or dashboard clients.

- code: groom/groom/docker_io.py::list_repo_dirs
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure,
  groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo

## Contract

- purpose: provide repository-picker checkout discovery for workflows whose workspace volume is known.
- input: `volume` is the Docker workspace volume name mounted read-only at `/vol` for the duration of discovery.
- consistency: repository discovery returns volume-relative parent directories for every `.git` directory found one or two directory levels below the volume root.
- consistency: repository discovery returns `[]` when the Docker discovery process exits non-zero or when no matching `.git` directories are found.
- consistency: single-repository lookup returns the first sorted checkout directory, or `""` when repository discovery is empty.
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
- abstract: false
- does: discover git checkout roots inside a workspace volume and return their volume-relative directories for [repository menu data](../repository-menu-data.md).
- does: builds a shell-free `docker run` command using `alpine:3.20` and `find /vol -mindepth 1 -maxdepth 2 -name .git -type d`.
- does: accepts only trimmed stdout paths beginning with `/vol/` and ending with `/.git`, then strips those sentinels.
- does: sorts accepted volume-relative checkout directories ascending before returning them.
- raises: process-launch exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) propagate.
- raises: timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) propagate.
- returns: Docker non-zero completion is converted to an empty list.
- returns: sorted volume-relative checkout directories, or `[]` when no matching checkout directories are found or no stdout lines are accepted.
- code: groom/groom/docker_io.py::list_repo_dirs
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure,
  groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo
- args:
  - `volume`: Docker workspace volume name mounted read-only at `/vol` for the throwaway discovery container.

### find-repo-dir

- sig: `find_repo_dir(volume: str) -> str`
- abstract: false
- does: delegates repository discovery and ordering to [list-repo-dirs](#list-repo-dirs).
- does: returns the first discovered checkout directory when discovery is non-empty.
- does: returns `""` when discovery returns no checkout directories.
- raises: propagates process-launch exceptions inherited from [list-repo-dirs](#list-repo-dirs).
- raises: propagates timeout exceptions inherited from [list-repo-dirs](#list-repo-dirs).
- returns: the first sorted volume-relative checkout directory, or `""` when none is available.
- verify: json_path(path="$", equals="Acme")
- verify: json_path(path="$", equals="")
- code: groom/groom/docker_io.py::find_repo_dir
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure
- args:
  - `volume`: Docker workspace volume name passed unchanged to [list-repo-dirs](#list-repo-dirs).
