---
type: concept
slug: workspace-volume-file-writer
title: Workspace volume file writer
---
# Workspace volume file writer

Workspace volume file writer is the shared Docker-volume write operation used by the [gate-answering layer](gate-answering-layer.md) to persist an operator answer back into the selected [operator gate context file](../operator-gate-context-file.md) inside a workflow workspace volume. It is the write-side sibling of the [workspace volume file-content reader](workspace-volume-file-content-reader.md): it delegates destination validation to the [workspace volume relative path guard](workspace-volume-relative-path-guard.md), delegates process execution to the [Docker subprocess runner](docker-subprocess-runner.md), streams the complete replacement file text through standard input, and reports only whether the temporary writer process exited successfully.

- code: groom/groom/docker_io.py::write_file
- refs: [workspace volume relative path guard](workspace-volume-relative-path-guard.md), [Docker subprocess runner](docker-subprocess-runner.md), [gate-answering layer](gate-answering-layer.md), [operator gate context file](../operator-gate-context-file.md), [workspace volume file-content reader](workspace-volume-file-content-reader.md), [Groom Docker I/O module](groom-docker-io-module.md#write-file)

## Contract

- purpose: provide one bounded write primitive for callers that already know the target Docker volume, safe volume-relative file path intent, and complete replacement text.
- input volume: `volume` is a Docker volume name mounted read-write at `/vol` for the duration of the write; Groom does not pre-validate the volume name, and missing or unusable volumes are represented by the completed Docker process return code when Docker can start.
- input rel_path: `rel_path` is the single volume-relative destination path to replace or create; it is validated and normalized by the [workspace volume relative path guard](workspace-volume-relative-path-guard.md) before any writer process starts, then addressed as `/vol/{normalized_rel_path}` inside the throwaway container.
- input content: `content` is the exact complete replacement text for the destination file; the writer allows empty text, supplies the full value on process standard input, and does not trim, append, parse status lines, redact secrets, or transform line endings.
- path validation: accepted destination paths are relative, non-empty, contain no empty path segment, contain no parent traversal segment, and use `/` as the normalized separator before they are embedded below `/vol`.
- command: runs `docker run --rm -i -v {volume}:/vol alpine:3.20 cp /dev/stdin /vol/{normalized_rel_path}` through the [Docker subprocess runner](docker-subprocess-runner.md) with the shared Docker timeout and `content` supplied as `input_text`.
- output success: returns `true` only when the temporary writer process completes and exits with code `0`.
- output failure: returns `false` when the temporary writer process completes with a non-zero exit code, including missing-volume, missing-parent-directory, read-only-volume, permission-denied, image, destination-path, or Docker command failures represented as process exit codes; stdout and stderr are intentionally not interpreted by this layer.
- exception failure: raises `ValueError` before any writer process starts when `rel_path` is empty, absolute, root-prefixed, contains an empty path segment, or contains `..`.
- exception failure: process-launch failures and timeout failures from the [Docker subprocess runner](docker-subprocess-runner.md) are not converted to `false`; they surface to the caller.
- side effects: creates one throwaway read-write Docker container and may create or replace the destination file inside an existing parent directory in the mounted volume.
- non-effect: does not create missing parent directories, choose a workspace volume, build answer text, parse or mutate gate status, start or stop workflow containers, inspect containers, mutate Groom's in-memory workflow state, broadcast dashboard events, append logs, or write any host filesystem path directly.

## Fields

### field-volume

- type: Docker volume name string
- default: none
- required: true
- meaning: names the workspace volume mounted read-write into the temporary writer container at `/vol`.
- validation: not validated by this writer before Docker receives it; Docker reports missing, inaccessible, or malformed volume outcomes through either a completed non-zero process or a subprocess-layer exception.

### field-rel-path

- type: volume-relative file path string
- default: none
- required: true
- meaning: names the single file destination below the mounted `/vol` root.
- validation: normalized and constrained by the [workspace volume relative path guard](workspace-volume-relative-path-guard.md) before the Docker command is built.

### field-content

- type: `str`
- default: none
- required: true
- meaning: complete file body to stream to the selected destination as standard input.
- preservation: sent to the subprocess runner unchanged, including empty strings, trailing whitespace, newlines, Markdown sections, status lines, and operator answer paragraphs.

### field-return-value

- type: `bool`
- default: none
- required: true
- meaning: `true` means the temporary writer process exited `0`; `false` means it completed with a non-zero exit code.
- limitation: does not include stderr, stdout, or a failure category; callers that need operator-facing messages map the boolean at their own layer.

## Methods

### write-file

- sig: `write_file(volume: str, rel_path: str, content: str) -> bool`
- abstract: false
- raises: `ValueError` for unsafe relative paths; process launch and timeout exceptions from the subprocess layer are intentionally surfaced.
- returns: the [field-return-value](#field-return-value) contract: `true` only when the temporary writer process exits `0`, otherwise `false` for completed non-zero processes.
- code: groom/groom/docker_io.py::write_file
- args: `volume`; required; no default; Docker volume mounted read-write at `/vol` for this one write.
- args: `rel_path`; required; no default; destination path validated by the [workspace volume relative path guard](workspace-volume-relative-path-guard.md) before becoming `/vol/{rel_path}`.
- args: `content`; required; no default; complete replacement text streamed to the writer process standard input unchanged.

Writes one caller-selected file inside one Docker volume and gives callers only the success boolean for the completed write process.

#### Effects

- calls: [workspace volume relative path guard](workspace-volume-relative-path-guard.md#safe-relpath) exactly once before constructing the container destination path.
- calls: [Docker subprocess runner](docker-subprocess-runner.md#run) exactly once when path validation succeeds.
- command: passes `docker run --rm -i -v {volume}:/vol alpine:3.20 cp /dev/stdin /vol/{validated_rel_path}` as a tokenized argv list to the subprocess runner.
- stdin: passes the full `content` value to the subprocess runner as the child process standard-input payload.
- timeout: uses the shared Docker I/O timeout of 20 seconds through the subprocess runner.
- writes: asks the temporary container to copy standard input into exactly the validated destination path below `/vol`.
- converts: completed non-zero process exits to `false` without inspecting stdout or stderr.
- preserves: the supplied content exactly at this layer; any status change, answer append, redaction, or normalization must already be present in the caller-built text.
- does not mutate: workflow containers, workflow registry state, gate records, sidecar connections, dashboard clients, logs, or host filesystem paths outside the mounted Docker volume.

## Algorithm

- step: Receive a Docker volume name, caller-selected destination path, and complete replacement text from the caller.
- step: Validate and normalize `rel_path` with the [workspace volume relative path guard](workspace-volume-relative-path-guard.md); stop with `ValueError` if the path is unsafe.
- step: Build a read-write Docker volume mount at `/vol` and a destination argument of `/vol/{validated_rel_path}`.
- step: Run a short-lived Alpine container whose command copies `/dev/stdin` to that destination, supplying `content` as process input through the shared Docker subprocess runner and timeout.
- step: Return `true` when the completed process return code is `0`; otherwise return `false`.

## Failure Behavior

- unsafe path: raises `ValueError` before Docker is invoked.
- missing parent directory: returns `false` when the copy process completes with a non-zero status.
- unreadable or read-only volume: returns `false` when Docker reports the write failure as a completed non-zero process.
- missing or unusable volume: returns `false` when Docker reports the failure as a completed non-zero process.
- Docker executable launch failure: propagates the subprocess-layer exception.
- timeout: propagates the subprocess-layer timeout exception.
- empty content: writes an empty file when Docker and the destination path allow it; success is still determined only by process exit code.

## Consumers

- uses: [gate-answering layer](gate-answering-layer.md) writes the answered [operator gate context file](../operator-gate-context-file.md) back into the workflow workspace volume after its stale-status guard passes and maps a `false` result to `AnswerResult(ok=False, message="failed to write answer")`.
- not used by: dashboard file-content browsing, sidecar file reads, discovery scans, repository listing, diff rendering, or host filesystem writes; those paths use read-only Docker helpers or sidecar APIs instead.
