---
type: concept
slug: sidecar-turn-pulling
title: Sidecar turn pulling
---
# Sidecar turn pulling

Sidecar turn pulling is the transport that retrieves a container's turn-record surface from the sidecar socket and mirrors it into the host archive. A run inside a container writes turn records to a run dir on the container's volume, which the host cannot directly read; the container is discarded when the run ends, destroying the only copy of records that explain a livelock or crash. Sidecar turn pulling gets that evidence out by having the container announce new turns via the socket, the host pulls the files into a staging tree, and then archives them using the same rules as local runs. The staging tree is a cache, not a second archive — it keeps the bytes already fetched so re-pulls ask only for files whose length has changed, and deleting it costs one slow pull and nothing else.

The puller stays non-authoritative by design: if it never connects, or a pull fails halfway, that container's records are simply absent from the archive. Nothing in the pulling path may raise into the socket loop, because the loop is also responsible for the live frames the human is watching.

- code: groom/groom/sidecar_turns.py
- tests: groom/tests/test_sidecar_turns.py

## Contract

Runs announced via the [sidecar websocket](../sidecar-websocket-frame.md) are pulled asynchronously without blocking the receive loop. Announces coalesce into at most two passes per container via in-flight state tracking: `schedule()` enqueues the first pass if none is in flight, and if another announce arrives while a pull is running, a single re-run is queued behind it instead of one pass per frame.

Fetched run dirs are mirrored under `<archive-root>/.incoming/<container-id>/<run>` before `harvest_run` archives them. Pulled files are written to a `.part` temp file and atomically moved into place, so an interrupted pull cannot leave a half-file the next harvest would digest as though it were the whole turn. One pull is bounded by `MAX_PULL_BYTES` (default 256MB, configurable via `GROOM_TURN_PULL_MAX_BYTES`), so a long run's ever-growing dir is pulled in multiple passes.

`schedule()` does not wait for the pull to complete; it returns immediately while the async task runs, because the caller is the socket receive loop and a blocking pull would stall the `progress` and gate frames the human watches. An announce with `final=True` marks the pull so that after the pull chain quiets, the entire staging dir for that container is dropped — everything worth keeping is already archived.

The puller does not raise into the socket loop on any failure; a missing sidecar connection, a halfway-failed pull, a timeout, or any other error simply means that container's records are absent from the archive. This non-authoritative design prevents one container's problems from breaking the host's ability to watch other runs.

## Methods

### method-staging_root

- sig: `staging_root() -> Path`
- abstract: false
- does: return the archive-relative path where fetched run dirs are mirrored during pulling.
- returns: `Path` pointing to `<transcripts_root>/.incoming`, the cache directory under the archive root.
- verify: visible(locator="<transcripts_root>/.incoming")
- code: groom/groom/sidecar_turns.py::staging_root
- tests: groom/tests/test_sidecar_turns.py::test_staging_root_returns_archive_incoming_dir

### method-pull

- sig: `async pull(conn, *, run: str = "", run_id: str = "", workflow: str = "") -> int`
- abstract: false
- does: mirror one container's run-record surface from the sidecar into the staging tree and archive it.
- raises: all exceptions are caught and logged at debug level and do not propagate.
- returns: count of records archived by `harvest_run` on the staged tree.
- code: groom/groom/sidecar_turns.py::pull
- tests: groom/tests/test_sidecar_turns.py::test_pull_lists_files_from_sidecar
- persistence: run-records — fetched turn records are written to the staging tree at `<staging>/<container_id>/<run>/<path>`.
- verify: persists(subject="fetched turn records in staging tree")
- idempotency: staged-files — files already staged at the reported size are skipped.
- verify: unchanged(subject="already-staged files at the same size")
- idempotency: re-run — re-running the pull on the same run fetches only new or changed files.
- verify: unchanged(subject="already-fetched files after re-run")

The method fetches the file listing via `conn.rpc("listTurns")`, then fetches each missing or changed file via `conn.rpc("readTurnFile")` in chunks (each chunk base64-encoded, each read bounded by `RPC_TIMEOUT` of 30 seconds). Each fetched file is written atomically: first to a `.part` temp file, then moved into place, so an interrupted pull cannot leave a half-file for the next harvest to digest. One pull respects the `MAX_PULL_BYTES` budget (default 256MB), breaking out if budget is exhausted; queueing a re-run is the caller's responsibility via `schedule()`. At the end, the method calls `harvest_run()` on the staged tree to archive it using the same rules as local runs.

### method-schedule

- sig: `schedule(conn, *, run: str = "", run_id: str = "", workflow: str = "", final: bool = False) -> None`
- abstract: false
- does: enqueue a pull without waiting for it.
- does: return immediately while the pull completes asynchronously.
- code: groom/groom/sidecar_turns.py::schedule
- tests: groom/tests/test_sidecar_turns.py::test_schedule_enqueues_async_without_blocking
- emits: one async task is enqueued in the event loop for the container if no pull is already in flight.
- verify: emitted(event="pull_task_enqueued", count=1)

This method is called from the socket receive loop to avoid blocking on a long pull while live `progress` and gate frames are pending. It takes the same connection and run identifiers as `pull()`, plus `final=True` to mark the pull as the one following a run reaching terminal state.

If no pull is already in flight for the container, the method creates one and enqueues it as an async task, recording the task so it is not collected mid-await. If a pull is already in flight, it sets a flag to re-run it once it quiets, so a burst of announces coalesces into at most two passes. If `final=True`, it marks the run so that after the pull chain quiets, the staging dir for that container is dropped.

