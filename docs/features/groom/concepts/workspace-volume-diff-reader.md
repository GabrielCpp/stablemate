---
type: concept
slug: workspace-volume-diff-reader
title: Workspace volume diff reader
---
# Workspace volume diff reader

Workspace volume diff reader is the fallback implementation used by the [serve workspace diff](../http/groom.md#serve-workspace-diff) invocation when the connected sidecar cannot provide [workspace diff data](../workspace-diff-data.md). It reads one checkout inside a known workspace Docker volume through a throwaway read-only git container, delegates process execution to the [Docker subprocess runner](docker-subprocess-runner.md), and returns raw unified working-tree diff text without mutating the workflow container, repository, sidecar registry, or dashboard clients. When no checkout is supplied, it depends on the [workspace volume repository-directory reader](workspace-volume-repository-directory-reader.md) to choose the first discovered checkout.

- code: groom/groom/docker_io.py::git_diff
- verify: groom/tests/test_app.py::test_diff_endpoint_passes_repo_through,
  groom/tests/test_docker_io.py::test_git_diff_returns_empty_when_no_repo_found,
  groom/tests/test_docker_io.py::test_git_diff_returns_stdout_on_success,
  groom/tests/test_docker_io.py::test_git_diff_returns_empty_on_git_failure

## Contract

- purpose: provide a volume-read fallback for dashboard diff requests when the live sidecar socket is absent, failed, or errored.
- input: `volume` is the Docker workspace volume name mounted read-only at `/vol` for the duration of the read.
- input: `repo_dir` is a volume-relative checkout directory; `""` asks the reader to select the first git checkout discovered in the workspace volume.
- validation: this reader does not sanitize or normalize an explicit `repo_dir`; first-party callers supply values from repository discovery or the repository picker.
- output: returns raw unified diff text for the selected checkout's working tree compared with `HEAD`, suitable for [workspace diff data](../workspace-diff-data.md).
- output: returns `""` when no checkout is found, the Docker reader process exits non-zero, the git diff command exits non-zero, or no diff text is available.
- repository selection: an explicit `repo_dir` is used unchanged as the checkout under `/vol`; an empty `repo_dir` is resolved through the first-repository lookup before attempting the diff.
- command: runs a throwaway `alpine/git:2.43.0` container with the workspace volume mounted read-only at `/vol`, `safe.directory=*`, working directory `/vol/{repo_dir}`, and `git diff HEAD` as the only diff command.
- command execution: delegates process launch, text stdout/stderr capture, timeout enforcement, and return-code capture to the [Docker subprocess runner](docker-subprocess-runner.md).
- timeout: the Docker command uses the shared Docker I/O timeout of 20 seconds; timeout or process-launch exceptions are not converted by this reader.
- side effects: creates only a throwaway read-only Docker container for the read; it does not change files, workflow state, sidecar registry state, or dashboard clients.

## Methods

### git-diff

- sig: `git_diff(volume: str, repo_dir: str = "") -> str`
- abstract: Read one checkout's working-tree-vs-`HEAD` unified diff from a workspace volume and return it as [workspace diff data](../workspace-diff-data.md).
- raises: none intentionally surfaced for missing repositories or non-zero git/Docker exit codes; process-launch and timeout exceptions from the shared Docker subprocess runner are not caught here.
- returns: raw unified diff stdout unchanged, or `""` for no selected checkout or non-zero git/Docker completion.
- code: groom/groom/docker_io.py::git_diff
- verify: groom/tests/test_docker_io.py::test_git_diff_returns_empty_when_no_repo_found
- verify: groom/tests/test_docker_io.py::test_git_diff_returns_stdout_on_success
- verify: groom/tests/test_docker_io.py::test_git_diff_returns_empty_on_git_failure
- volume: required Docker workspace volume name; mounted read-only at `/vol` for the throwaway git command.
- repo_dir: optional volume-relative checkout directory; default `""`; when empty, resolved through [find-repo-dir](workspace-volume-repository-directory-reader.md#find-repo-dir).
- calls: [find-repo-dir](workspace-volume-repository-directory-reader.md#find-repo-dir) when `repo_dir` is empty, and the [Docker subprocess runner](docker-subprocess-runner.md#run) for the throwaway git command.
- effects: creates a read-only temporary Docker container to inspect git state; performs no file writes, no dashboard broadcast, no sidecar RPC, and no workflow-container restart.
- steps:
  - If `repo_dir` is empty, ask the [first-repository lookup](workspace-volume-repository-directory-reader.md#find-repo-dir) for the checkout to diff.
  - If no checkout is available after that lookup, return `""` without starting a git container.
  - Run the read-only git container against `/vol/{repo_dir}` with `safe.directory=*` and `diff HEAD`.
  - If the git container exits non-zero, return `""`.
  - Otherwise return the container stdout unchanged, including an empty stdout when the checkout has no working-tree diff.
