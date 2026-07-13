---
type: concept
slug: container-running-state-check
title: Container running-state check
---
# Container running-state check

Container running-state check is the `is_running` public member of the [Groom Docker I/O module](groom-docker-io-module.md) and Groom's read-only boolean lifecycle probe for one Docker container id. The [gate-answering layer](gate-answering-layer.md) uses it after a successful answer-file write to distinguish the normal in-place wake path from the [stopped container start fallback](stopped-container-start-fallback.md), while the check itself delegates raw metadata lookup to the [Docker inspection reader](docker-inspection-reader.md) and reads only the `State.Running` value from the [Docker inspect container object](../docker-inspect-container-object.md).

- code: groom/groom/docker_io.py::is_running
- refs: [Groom Docker I/O module](groom-docker-io-module.md), [Docker inspection reader](docker-inspection-reader.md), [Docker inspect container object](../docker-inspect-container-object.md)

## Contract

- purpose: answer whether one selected workflow container is currently running so callers can decide whether a restart is necessary after an otherwise successful operation.
- input: `container_id` is a required string passed unchanged to the Docker inspection reader; this concept does not normalize, truncate, validate, or map it to another workflow identity.
- identity semantics: accepts whatever full or short id Docker accepts for inspection; a successful result only reports process liveness for that Docker target and does not prove that the target is still a workhorse workflow container.
- lookup: obtains raw container metadata from the [Docker inspection reader](docker-inspection-reader.md), which returns the first parsed `docker inspect` object or no metadata.
- observed field: reads the nested `State.Running` value from the [Docker inspect container object](../docker-inspect-container-object.md#field-state-running).
- call boundary: calls exactly one Groom source symbol, `docker_inspect`, and performs no direct Docker subprocess call itself.
- defaulting: Docker inspection failures represented by the reader as no metadata, including non-zero `docker inspect`, malformed JSON, and an empty inspect array, are all treated as not running.
- output: returns `True` only when inspection metadata is present and the nested `State.Running` value is truthy.
- output: returns `False` when inspection metadata is absent, the `State` object is missing, the `Running` field is missing, or the `Running` value is falsey.
- failure boundary: subprocess launch failures, Docker timeout failures, shape errors raised by the Docker inspection reader, and present-but-non-mapping `State` values are not caught here; callers that need domain-specific results must handle those exceptions outside the check.
- side effects: performs only a Docker metadata read through the inspection reader; it does not start, stop, prune, exec into, or mutate the container, and it does not change Groom's in-memory workflow registry or dashboard clients.
- concurrency: has no cache, lock, or retry state; each call observes the Docker inspection answer available at that instant.

## Methods

### is-running

- sig: `is_running(container_id: str) -> bool`
- abstract: false
- raises: propagates subprocess launch and timeout exceptions from the Docker inspection reader path; propagates ordinary metadata-shape errors when present metadata contains a non-mapping `State` value.
- returns: `True` only for present inspection metadata with truthy `State.Running`; otherwise `False` for absent metadata, absent `State`, absent `Running`, or falsey `Running`.

## Algorithm

- step: Request Docker inspection metadata for `container_id` through the [Docker inspection reader](docker-inspection-reader.md).
- step: If no inspection metadata is returned, return `False`.
- step: Read the metadata's `State` mapping, using an empty mapping only when the `State` key is absent.
- step: Read the `Running` value from that state mapping and convert it to a boolean; truthy non-boolean values are treated as running, falsey non-boolean values are treated as not running, and a present `State` value that does not expose mapping-style lookup propagates that shape error.
- step: Return that boolean as the running-state answer.

## Callers

- used by: [Gate-answering layer](gate-answering-layer.md) calls this check after the answered gate file has been written and the in-memory gate has been cleared.
- caller effect: when this check returns `True`, the gate-answering layer returns `ok=true` with message `answered` and does not call Docker start.
- caller effect: when this check returns `False`, the gate-answering layer attempts the [stopped container start fallback](stopped-container-start-fallback.md).
- caller coverage: `groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running` verifies the no-restart branch when this check reports running.
- caller coverage: `groom/tests/test_gates.py::test_answer_gate_restarts_when_container_stopped` verifies the fallback-start branch when this check reports not running.
