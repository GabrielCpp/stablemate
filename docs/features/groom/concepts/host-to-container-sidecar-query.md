---
type: concept
slug: host-to-container-sidecar-query
title: Host-to-container sidecar query
---
# Host-to-container sidecar query

Host-to-container sidecar query is the discovery-time Docker I/O pull path that asks one running [workflow container](workflow-container.md) for its current [sidecar snapshot data](../sidecar-snapshot-data.md) by executing [`groom-sidecar --query`](../groom-sidecar.md#groom-sidecar-root) inside that container. The [per-container discovery resolver](workflow-discovery-scan.md#method-resolve-container) uses this layer only after Docker inspect has confirmed the container is running; a successful JSON object feeds the [sidecar query snapshot transition](workflow-state.md#transition-sidecar-query-or-discovery-snapshot), while every represented query-unavailable case returns `None` so the resolver can use [volume reconstruction](workflow-state.md#transition-volume-reconstruction) instead. The query uses Groom's [Docker exec runner](docker-exec-runner.md), which ultimately relies on the [Docker subprocess runner](docker-subprocess-runner.md) for shell-free process execution, text output capture, and timeout enforcement.

- code: groom/groom/docker_io.py::sidecar_query
- verify: groom/tests/test_docker_io.py::test_sidecar_query_parses_snapshot_json
- verify: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_nonzero_exit
- verify: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_non_json_output
- verify: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_when_docker_missing
- verify: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_timeout
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container

## Contract

- purpose: provide a bounded host-to-container pull path for a running sidecar snapshot without reading named volumes through throwaway containers.
- input: `container_id` is a Docker container id string selected by the discovery resolver from the normalized [workflow container](workflow-container.md) id.
- command: runs `uv run groom-sidecar --query` inside the target container.
- exec argv: asks the [Docker exec runner](docker-exec-runner.md) to construct `docker exec -u nobody -e HOME=/claude-state <container_id> uv run groom-sidecar --query` before handing execution to the Docker subprocess layer.
- docker user: executes as container user `nobody`.
- environment: sets `HOME=/claude-state` for the exec process so the sidecar command resolves its tool environment consistently with the workflow entrypoint.
- timeout: inherits the [Docker exec runner](docker-exec-runner.md)'s default Docker I/O timeout of twenty seconds, enforced by the [Docker subprocess runner](docker-subprocess-runner.md).
- output: `dict[str, Any] | None`; a dictionary is the decoded stdout JSON object and is intended to satisfy the [sidecar snapshot data](../sidecar-snapshot-data.md) contract.
- success boundary: accepts only top-level JSON objects; arrays, strings, numbers, booleans, `null`, malformed JSON, non-zero Docker exits, and caught process exceptions all return `None`.
- fallback signal: `None` means the host could not obtain a usable sidecar query object; it does not distinguish stopped containers, missing Docker, timeout, legacy images, non-zero exits, malformed stdout, or non-object JSON.
- validation boundary: does not validate snapshot fields, gate entry shape, terminal precedence, or current-node semantics; the discovery state transition validates and applies the returned object.
- scope boundary: performs no Docker inspect, running-state check, sidecar websocket registration, volume reconstruction, or workflow-state mutation; callers decide when the query is allowed and how to apply or ignore the result.
- persistence: does not mutate Docker container state, volumes, the workflow registry, gate files, dashboard clients, or sidecar process state.

## Effects

- Calls: the first-party [Docker exec runner](docker-exec-runner.md) once with the supplied container id, command arguments `uv run groom-sidecar --query`, user `nobody`, environment `HOME=/claude-state`, and the default Docker I/O timeout; the exec runner delegates the completed argv to the [Docker subprocess runner](docker-subprocess-runner.md).
- Reads: the Docker exec result's return code and stdout text.
- Emits: `None` immediately when Docker exec raises a caught process/launch/timeout exception.
- Emits: `None` when Docker exec completes with a non-zero return code, including stopped containers, missing Docker access, or legacy sidecar images that do not support query mode.
- Parses: stdout as JSON only after a zero return code.
- Emits: the decoded object unchanged when the decoded top-level JSON value is a dictionary.
- Emits: `None` when stdout is non-JSON, JSON parsing raises a value error, or the decoded top-level value is not a dictionary.
- Preserves: stderr text, non-dictionary JSON values, malformed output details, and Docker exception details are not exposed to callers.
- Preserves: the target container's process state except for the short-lived exec process itself; the query does not start stopped containers or restart legacy sidecars.
- Delegates: interpretation of `current_node`, `terminal`, and `gates` fields to the [sidecar query snapshot transition](workflow-state.md#transition-sidecar-query-or-discovery-snapshot) instead of validating those fields at the Docker I/O boundary.

## Algorithm

- step: Invoke the [Docker exec runner](docker-exec-runner.md) for the target container with the sidecar query command, `nobody` user, and sidecar home environment.
- step: If Docker exec raises `OSError` or a subprocess exception, return `None`.
- step: If the completed process return code is non-zero, return `None`.
- step: Decode the completed process stdout as JSON.
- step: If decoding fails, return `None`.
- step: If the decoded value is a dictionary, return it unchanged.
- step: Return `None` for every decoded value that is not a dictionary.

## Methods

### method-sidecar-query

- sig: `sidecar_query(container_id: str) -> dict[str, Any] | None`
- abstract: false
- raises: no intentional exception for missing Docker, Docker exec timeout, non-zero Docker exit, malformed JSON stdout, or non-object JSON stdout; unexpected failures outside `OSError` and subprocess exceptions can propagate.
- returns: decoded [sidecar snapshot data](../sidecar-snapshot-data.md) as a dictionary when the in-container query command exits successfully and stdout is a JSON object; otherwise `None`.
- code: groom/groom/docker_io.py::sidecar_query
- verify: groom/tests/test_docker_io.py::test_sidecar_query_parses_snapshot_json
- verify: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_nonzero_exit
- verify: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_non_json_output
- verify: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_when_docker_missing
- verify: groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_timeout
- arg: `container_id`; type `str`; required; no default; identifies the running workflow container targeted by Docker exec.
- calls: [Docker exec runner](docker-exec-runner.md#docker_exec) with `args=["uv", "run", "groom-sidecar", "--query"]`, `user="nobody"`, and `env={"HOME": "/claude-state"}`.
- returns-none-when: Docker exec raises a caught `OSError` or subprocess exception, Docker exec returns a non-zero code, stdout is not JSON, or stdout decodes to a non-dictionary JSON value.
- returns-dict-when: Docker exec exits with return code `0` and stdout decodes to a top-level JSON object.

Runs exactly one host-to-container sidecar query for the supplied container id and translates every represented query-unavailable result into `None`. A returned dictionary is not field-validated here; the discovery state transition owns snapshot interpretation and fallback callers treat `None` as permission to reconstruct from mounted volumes.

## Failure behavior

- Container not running: represented by a non-zero Docker exec result or subprocess failure and returned as `None`.
- Docker unavailable: represented as `None` when process launch raises a caught `OSError`.
- Timeout: represented as `None` when the [Docker exec runner](docker-exec-runner.md) raises a caught subprocess timeout.
- Legacy sidecar: represented as `None` when the command exits non-zero because `groom-sidecar --query` is unavailable or fails.
- Non-JSON stdout: represented as `None` and does not propagate the parse error.
- JSON non-object stdout: represented as `None` even if the JSON text itself is valid.
