---
type: concept
slug: run-telemetry-archive-loop
title: Run telemetry archive loop
---
# Run telemetry archive loop

The archive loop is the background task that periodically examines expired runs and writes their telemetry to disk via the [archive module](groom-archive-module.md). It wakes on every application tick, checks whether `ARCHIVE_EVERY_S` seconds have elapsed since the last sweep, and if so, calls `archive.sweep()` to archive up to `RUNS_PER_PASS` expired runs oldest first. The loop runs in a thread off the async event loop so that blocking file I/O and database work do not stall the main server. Every exception is caught and logged; a single failed sweep does not halt the loop or impact server operation.

The loop is seeded on startup to run immediately rather than waiting `ARCHIVE_EVERY_S` seconds, so a fresh groom instance begins draining any pre-existing archival backlog as soon as it comes up.

- code: `groom/groom/app.py::_archive_loop`
- extends: [groom archive module](groom-archive-module.md)
- tests: `groom/tests/test_archive.py`, `groom/tests/test_sidecar_turns.py`

## Fields

### archive-every-s

- type: `float`
- default: `21600.0` (six hours)
- required: true
- semantics: The elapsed time in seconds between archive sweep passes. Loaded from the environment variable `GROOM_ARCHIVE_EVERY_S` and re-exported as `ARCHIVE_EVERY_S` in the app module.
- code: `groom/groom/app.py::ARCHIVE_EVERY_S`

### rules-tick-s

- type: `float`
- default: `1.0`
- required: true
- semantics: The interval in seconds between loop ticks. The loop wakes this often to check whether it is time to run a sweep, but only runs the sweep when the elapsed time since the last sweep exceeds `ARCHIVE_EVERY_S`.
- code: `groom/groom/app.py::RULES_TICK_S`

## Methods

### method-archive-loop

- sig: `_archive_loop() -> None`
- abstract: false
- does: Runs forever, waking on every `RULES_TICK_S` tick and executing `archive.sweep()` when `ARCHIVE_EVERY_S` seconds have elapsed since the last sweep
- does: Seeds the first sweep to run immediately by initializing `last` to `time.monotonic() - ARCHIVE_EVERY_S`
- does: Catches all exceptions from `sweep()` and logs them without propagation, so that archival failures do not impact server operation
- does: Logs the result of each sweep, including the count of archived runs, rows deleted, bytes written, and failed runs
- raises: none into the caller — all exceptions are logged and the loop continues
- verify: emitted(event="groom: archived")
- verify: persists(subject="run telemetry file on disk")
- code: `groom/groom/app.py::_archive_loop`

### method-spawn-archive

- sig: `_spawn_archive() -> None`
- abstract: false
- does: Creates and schedules the archive loop as an async task during server startup via the `on_startup` hook
- verify: created(subject="archive loop task in running tasks")
- raises: none intentionally raised
- verify: json_path(path="exception.type", absent=true)
- code: `groom/groom/app.py::_spawn_archive`

### method-stop-archive

- sig: `_stop_archive() -> None`
- abstract: false
- does: Cancels the archive loop task during server shutdown via the `on_shutdown` hook
- verify: absent(subject="archive loop task in running tasks")
- raises: none intentionally raised
- verify: json_path(path="exception.type", absent=true)
- code: `groom/groom/app.py::_stop_archive`

## Lifecycle

The archive loop is bound to the groom server's startup and shutdown:

1. **On server startup** (`_spawn_archive`): the loop task is created and added to the event loop's running tasks.
2. **During server operation**: the loop runs continuously, checking on every `RULES_TICK_S` interval whether to execute a sweep.
3. **On server shutdown** (`_stop_archive`): the loop task is cancelled, stopping further sweeps.

The loop is intentionally run in a thread via `asyncio.to_thread()` so that blocking operations (file I/O, database queries) do not stall the async event loop and keep the server responsive to client requests.

