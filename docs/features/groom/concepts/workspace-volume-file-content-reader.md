---
type: concept
slug: workspace-volume-file-content-reader
title: Workspace volume file-content reader
---
# Workspace volume file-content reader

Workspace volume file-content reader is the shared volume text-read operation used by the [serve workspace file content](../http/groom.md#serve-workspace-file-content) invocation when the connected sidecar cannot provide the selected file's text, by the [workflow discovery scan](workflow-discovery-scan.md) when it reads [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md), [sidecar run metadata](../sidecar-run-metadata.md), and awaiting gate files from Docker volumes, and by the [gate-answering layer](gate-answering-layer.md) before it checks whether a submitted answer is stale. It reads one validated path inside a known Docker volume through a throwaway read-only container, delegates path safety to the [workspace volume relative path guard](workspace-volume-relative-path-guard.md), delegates process execution to the [Docker subprocess runner](docker-subprocess-runner.md), and returns [workspace file content data](../workspace-file-content-data.md) text or absence without mutating the volume, workflow container, in-memory workflow state, sidecar registry, or dashboard clients.

- code: groom/groom/docker_io.py::read_file
- refs: [workspace volume relative path guard](workspace-volume-relative-path-guard.md), [Docker subprocess runner](docker-subprocess-runner.md), [workspace file content data](../workspace-file-content-data.md), [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md), [sidecar run metadata](../sidecar-run-metadata.md), [workflow discovery scan](workflow-discovery-scan.md), [gate-answering layer](gate-answering-layer.md), [Groom Docker I/O module](groom-docker-io-module.md#read-file)
- verify: groom/tests/test_app.py::test_file_endpoint_joins_repo_and_path_and_returns_content, groom/tests/test_app.py::test_file_endpoint_swallows_unsafe_path, groom/tests/test_app.py::test_file_content_prefers_sidecar_socket, groom/tests/test_discovery.py::test_find_gates_only_keeps_files_still_awaiting, groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes, groom/tests/test_gates.py::test_answer_gate_rejects_when_already_answered, groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running

## Contract

- purpose: provide one text-read primitive for volume-backed dashboard file content, Docker discovery metadata, live gate-file rereads, and other callers that already know the target Docker volume and volume-relative path.
- input: `volume` is the Docker volume name mounted read-only at `/vol` for the duration of the read; the reader performs no separate volume-name validation and lets Docker report missing or unusable volumes through the process result.
- input: `rel_path` is a non-empty volume-relative file path; dashboard file-content callers combine repository and file-path query values before passing it, while discovery and gate-answering callers pass paths already expressed relative to the target volume root.
- validation: applies the [workspace volume relative path guard](workspace-volume-relative-path-guard.md) before starting any container; accepted paths are relative, non-empty, contain no empty path segment, contain no parent traversal segment, and use `/` as the normalized separator.
- command: runs `docker run --rm -v {volume}:/vol:ro alpine:3.20 cat /vol/{validated_rel_path}` as one tokenized argv list with captured text output and the shared Docker timeout through the [Docker subprocess runner](docker-subprocess-runner.md).
- reader image: uses the shared Alpine image constant `alpine:3.20` for the temporary reader container.
- timeout: uses the shared Docker I/O timeout of 20 seconds for the complete container create/read/remove subprocess.
- output: returns the selected file's raw text exactly as emitted on stdout by the reader process when the process exits with code `0`; this may be an empty string for an empty file.
- output: returns `None` when the reader process exits non-zero, including missing-file and unreadable-file cases.
- failure: raises `ValueError` when `rel_path` is empty, absolute, contains an empty path segment, or contains `..`; the HTTP invocation converts that failure to an empty `200 OK` response.
- failure: subprocess launch failures and timeout failures are not converted by this reader; callers that need endpoint-specific empty responses must catch them outside this function.
- side effects: creates only a throwaway read-only Docker container for the read; it does not write files, start or stop workflow containers, change workflow state, change sidecar registry state, broadcast websocket frames, or write logs.
- no fallback policy: does not choose between sidecar and volume sources, select a repository, choose a default run directory, parse JSON, parse gate status, or clear stale gates; every caller owns its own fallback and interpretation of returned text or `None`.
- trust boundary: treats `volume` as caller/Docker-derived data and validates only the file path; malformed, missing, or inaccessible volume names are represented by Docker process failure rather than by preflight validation.

## Fields

### field-volume

- type: Docker volume name string
- default: none
- required: true
- meaning: names the Docker volume mounted into the temporary reader container at `/vol` with read-only access.
- validation: not validated by this reader; Docker decides whether the named volume exists and can be mounted.

### field-rel-path

- type: volume-relative file path string
- default: none
- required: true
- meaning: names the single file to read below the mounted `/vol` root.
- validation: normalized and constrained by the [workspace volume relative path guard](workspace-volume-relative-path-guard.md) before the reader process starts.

### field-return-value

- type: `str | None`
- default: none
- required: true
- meaning: carries raw stdout text for a successful read, including the empty string for an empty file, or `None` for any completed reader process whose exit code is non-zero.

### field-reader-image

- type: Docker image reference string
- default: `alpine:3.20`
- required: true
- code: groom/groom/docker_io.py::ALPINE_IMAGE
- meaning: supplies the image used for the throwaway read-only container that executes `cat` against the mounted volume path.

### field-timeout

- type: seconds as `int`
- default: `20`
- required: true
- code: groom/groom/docker_io.py::DOCKER_TIMEOUT
- meaning: bounds the subprocess that starts the reader container and captures its output.

## Methods

### read-file

- sig: `read_file(volume: str, rel_path: str) -> str | None`
- abstract: false
- raises: `ValueError` for unsafe relative paths before any reader process is started; process launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) can propagate unchanged.
- returns: the [field-return-value](#field-return-value) contract: raw stdout text on reader exit `0`, otherwise `None`.
- code: groom/groom/docker_io.py::read_file
- verify: groom/tests/test_app.py::test_file_endpoint_joins_repo_and_path_and_returns_content
- verify: groom/tests/test_app.py::test_file_endpoint_swallows_unsafe_path
- verify: groom/tests/test_discovery.py::test_find_gates_only_keeps_files_still_awaiting
- verify: groom/tests/test_gates.py::test_answer_gate_rejects_when_already_answered
- args: `volume`; required; no default; Docker volume mounted read-only at `/vol` for this one read.
- args: `rel_path`; required; no default; file path validated by the [workspace volume relative path guard](workspace-volume-relative-path-guard.md) before becoming `/vol/{rel_path}`.

Reads one caller-selected file from one Docker volume and gives callers the raw text or a missing/unreadable signal.

#### Effects

- calls: [workspace volume relative path guard](workspace-volume-relative-path-guard.md#safe-relpath) exactly once before constructing the container file path.
- calls: [Docker subprocess runner](docker-subprocess-runner.md#run) exactly once when path validation succeeds.
- command: passes `docker run --rm -v {volume}:/vol:ro alpine:3.20 cat /vol/{validated_rel_path}` as a tokenized argv list to the subprocess runner.
- timeout: uses the shared Docker I/O timeout of 20 seconds through the subprocess runner.
- reads: the selected mounted file only when Docker can create the temporary container and `cat` can read the destination.
- converts: completed non-zero process exits to `None` without inspecting stderr or raising a domain error.
- preserves: completed zero-exit stdout exactly, with no stripping, JSON parsing, character-set conversion beyond the subprocess text capture, path-prefix trimming, or empty-string normalization.
- does not mutate: Docker volumes, workflow containers, workflow registry state, gate records, sidecar connections, dashboard clients, or logs.

## Algorithm

- step: Receive a Docker volume name and caller-selected relative file path from an HTTP, discovery, or gate-answering caller.
- step: Validate `rel_path` with the [workspace volume relative path guard](workspace-volume-relative-path-guard.md) before constructing the container destination path; stop with `ValueError` if the path is unsafe.
- step: Build a read-only Docker volume mount at `/vol` and a destination argument of `/vol/{validated_rel_path}`.
- step: Run a short-lived Alpine container whose command is `cat` against that destination, capturing stdout, stderr, and the process exit code through the shared Docker subprocess runner and timeout.
- step: Return `None` when the completed process exit code is not `0`; otherwise return stdout unchanged.

## Failure Behavior

- unsafe path: raises `ValueError` before Docker is invoked.
- missing file: returns `None` when the reader process completes with a non-zero status.
- unreadable file: returns `None` when the reader process completes with a non-zero status.
- missing or unusable volume: returns `None` when Docker reports the failure as a completed non-zero process.
- Docker executable launch failure: propagates the subprocess-layer exception.
- timeout: propagates the subprocess-layer timeout exception.
- empty file: returns `""` when `cat` exits with code `0` and emits no stdout.

## Consumers

- uses: [serve workspace file content](../http/groom.md#serve-workspace-file-content) calls this reader only after the sidecar file-content request is unavailable or fails, then serializes the returned text as [workspace file content data](../workspace-file-content-data.md) or an empty body.
- uses: [workflow discovery scan](workflow-discovery-scan.md) calls this reader for the latest run's `checkpoint.json` [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md), the latest run's `run.json` [sidecar run metadata](../sidecar-run-metadata.md), and candidate awaiting gate files after the sidecar query path is unavailable or impossible for a stopped container.
- uses: [gate-answering layer](gate-answering-layer.md) calls this reader while holding the per-gate answer lock so it can reject answers whose [operator gate context file](../operator-gate-context-file.md) is no longer awaiting operator input.
- not used by: the connected sidecar happy path for file content; [serve workspace file content](../http/groom.md#serve-workspace-file-content) skips this reader when a sidecar `getFile` call returns a result.
