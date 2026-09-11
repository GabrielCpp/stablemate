---
type: concept
slug: attendant-session-persistence
title: Attendant session persistence
---
# Attendant session persistence

The `attend_sessions` table holds the dispatch record for every attendant groom has spawned at a stopped or failed run. It is a create-once, keep-forever ledger — rows are never deleted, only updated to record the attendant's completion. The table is queried by the rules engine to determine whether a run already has an outstanding attendant, and by the UI to navigate between a blocked run and its attendants.

- code: `groom/groom/store.py`
- extends: [Attendant dispatch](groom-attend.md)
- rule: this concept owns the per-method contract for every `attend_*` function — signature, `does:`, `returns:`, `verify:`, `code:`. [Telemetry store (SQLite)](groom-store.md)'s own `attend_*` entry documents `attend_sessions` only as one of the store's four tables, alongside `spans`/`metrics`/`logs`/`turns`; it must not be read as a second, independent spec for any one method.
- prefers: [method: attend_running_for_run](#method-attend_running_for_run)
- deprecates: [attend_* (attendant gate support)](groom-store.md#attend_-attendant-gate-support)
- tests: `groom/tests/test_store.py`
- detail: [concept: Session states](#concept-session-states) — the closed enumeration an `attend_sessions.status` value is drawn from; one of two states, no third

## concept: Session states

The closed enumeration an attendance's `status` column is drawn from. An attendance exists in exactly one of two states; there is no third. The two states are module-level constants in `groom/groom/store.py`, bound at import time, and are the only values the dispatch and finish methods ever write to that column — [`attend_start`](#method-attend_start) and [`attend_append_session`](#attend_append_session) write `ATTEND_RUNNING`; [`attend_finish`](#attend_finish) writes `ATTEND_COMPLETED`.

- code: `groom/groom/store.py::ATTEND_RUNNING`
- code: `groom/groom/store.py::ATTEND_COMPLETED`
- tests: `groom/tests/test_attend.py::test_a_row_is_running_until_the_owner_finishes_it`

### field: ATTEND_RUNNING

- type: `str`
- default: `"running"`
- required: true
- semantics: groom has dispatched an attendant and not yet observed it exit — the attendant's process is presumed alive
- semantics: the claim is conditional — a headless attendant's pid may have died since the last query, which is what boot recovery re-checks at startup via [`attend_orphans`](#attend_orphans) so a stale dispatch is re-armed with a fresh session rather than left as an orphan the rules engine would never reclaim
- semantics: persisted to `attend_sessions.status` by [`attend_start`](#method-attend_start) on dispatch and by [`attend_append_session`](#attend_append_session) on boot-recovery re-arm; the row is rewritten in place rather than re-inserted, so a recovery never produces a duplicate
- code: `groom/groom/store.py::ATTEND_RUNNING`
- verify: json_path(path="status", equals="running")
- tests: `groom/tests/test_attend.py::test_a_row_is_running_until_the_owner_finishes_it`

### field: ATTEND_COMPLETED

- type: `str`
- default: `"completed"`
- required: true
- semantics: the attendant exited or groom stopped it — the row is terminal and never re-flipped to `ATTEND_RUNNING` short of a fresh dispatch keyed by a different `job_id`
- semantics: the row remains queryable after completion — [`attend_latest_for_run`](#method-attend_latest_for_run), [`attend_recent`](#method-attend_recent) and [`attend_by_session`](#method-attend_by_session) return completed rows alongside running ones, so the UI can still navigate from a blocked run to a past attendant that already exited
- semantics: persisted to `attend_sessions.status` by [`attend_finish`](#attend_finish) along with the exit code, completion timestamp, and the run's terminal gate or failure state captured at the moment the attendant left
- code: `groom/groom/store.py::ATTEND_COMPLETED`
- verify: json_path(path="status", equals="completed")
- tests: `groom/tests/test_attend.py::test_a_row_is_running_until_the_owner_finishes_it`

## Table and row conversion

### method: _attend_row

- sig: `(row: sqlite3.Row) -> dict[str, Any]`
- does: copy every column of the row into a dict, preserving the row's keys
- verify: keys_unchanged(subject="row dict keys")
- does: decode the `session_ids` column from its stored JSON string into a list of strings, falling back to an empty list when the stored value is malformed JSON, empty, or absent
- verify: json_path(path="session_ids", matches="^\\[.*\\]$")
- returns: a dict whose `session_ids` field is `list[str]` rather than the stored JSON string
- code: `groom/groom/store.py::_attend_row`

Session ids are appended when an attendance is resumed after a groom restart, making the full history queryable. The list order is preserved from the JSON, so the freshest session id is at index `-1` because [`attend_append_session`](#attend_append_session) appends rather than inserts.

## Dispatch lifecycle

### method: attend_start
- sig: `(job_id: str, *, run_id: str = "", workflow: str = "", run_dir: str = "", workspace: str = "", kind: str = "", reason: str = "", node: str = "", gate_path: str = "", session_id: str = "", pid: int | None = None, started_at: float | None = None) -> None`
- does: insert or replace a row with `status = running`, capturing the dispatch metadata before the attendant's first byte of output
- returns: nothing
- raises: sqlite3.Error if the INSERT OR REPLACE fails after one reopen attempt by the [@_resilient](../concepts/_store-class.md#method-_resilient) wrapper
- idempotency: attend-sessions-row — INSERT OR REPLACE on job_id, so re-calling with the same job_id replaces the row rather than duplicating
- code: `groom/groom/store.py::attend_start`
- detail: [reason method](../attend-job.md#reason)
- verify: json_path(path="status", equals="running")
- tests: `groom/tests/test_attend.py::test_a_row_is_running_until_the_owner_finishes_it`

The session id is minted by groom and passed to the CLI invocation, not scraped from it. This ensures the row exists from the moment the process does, making the dispatch discoverable even if the process crashes immediately.

### attend_append_session
- sig: `(job_id: str, session_id: str, pid: int | None = None) -> None`
- does: append a fresh session id to the `session_ids` list and reset status to `running`, clearing `exit_code` and `ended_at` — used by boot recovery when a groom restart finds an attendance whose pid is stale
- returns: nothing
- code: `groom/groom/store.py::attend_append_session`
- verify: persists(subject="attend_sessions row", field="session_ids", value="appended")
- verify: persists(subject="attend_sessions row", field="status", value=ATTEND_RUNNING)

The row stays one logical attendance (same `job_id`) across a groom restart; respawning appends to the session history rather than creating a second row. This keeps the repair linked to the original dispatch context.

### attend_finish
- sig: `(job_id: str, *, exit_code: int | None = None, released_state: str = "", ended_at: float | None = None) -> None`
- does: update a row to `status = completed` and record the exit code, completion timestamp, and terminal state (a JSON string carrying the run's final gate or failure status at the moment the attendant left)
- returns: nothing
- code: `groom/groom/store.py::attend_finish`
- verify: persists(subject="attend_sessions row", field="status", value=ATTEND_COMPLETED)
- verify: persists(subject="attend_sessions row", field="exit_code")
- verify: persists(subject="attend_sessions row", field="ended_at")

Called by the thread that owned the process; in headless mode this is the ownership daemon spawned at dispatch.

## Query interface

### method: attend_running_for_run
- sig: `(run_id: str) -> dict[str, Any] | None`
- does: return the attendant currently on this run, if there is one, narrowed to `status = running`
- verify: json_path(path="status", equals="running")
- returns: the converted row or `None` if no running attendance exists
- verify: json_path(path="session_ids", matches=".+")
- code: `groom/groom/store.py::attend_running_for_run`
- detail: [Attendant session persistence](attendant-session-persistence.md)

This is the whole dispatch rule: one attendant per run, serial. No timer, no budget — a run still stopped when its attendant finishes gets another dispatch on the next rules tick.

### method: attend_latest_for_run
- sig: `(run_id: str) -> dict[str, Any] | None`
- does: return the most recent attendance on this run, running or not — the one link the UI pane uses
- returns: the converted row or `None` if no attendance exists
- code: `groom/groom/store.py::attend_latest_for_run`
- verify: json_path(path="job_id", equals="the job_id of whichever row for this run_id has the latest started_at")

The newest attendance by `started_at`, regardless of completion status.

### attend_latest_by_run
- sig: `() -> dict[str, dict[str, Any]]`
- returns: `run_id -> attendance dict` mapping; a run with no attendance is not in the result
- code: `groom/groom/store.py::attend_latest_by_run`

Returns the latest attendance per run, keyed by run_id, in one query rather than one per run — a
shape built for rendering the whole fleet in a single pass. Consumed by the rules engine rendering
the fleet projection, which links each blocked run to its attendant.

### method: attend_recent
- sig: `(limit: int = 200) -> list[dict[str, Any]]`
- does: return the latest attendances, newest first, without pagination or deletion
- verify: json_path(path="[0].job_id", matches=".+")
- returns: ordered list of converted rows, newest first, capped at `limit`
- verify: json_path(path="[0].session_ids", matches="^\\[.*\\]$")
- code: `groom/groom/store.py::attend_recent`
- detail: [Attendant session persistence](attendant-session-persistence.md)

The corpus is the point. Reading back a season of attendances is how a recurring cause in the workflows shows up at all. Attendances older than the telemetry retention window are kept indefinitely — deleting them would be exactly the bug this solve for.

### method: attend_get
- sig: `(job_id: str) -> dict[str, Any] | None`
- does: return the attendance with the given job id
- verify: json_path(path="job_id", equals="the job_id parameter passed to the method")
- returns: the converted row or `None` if it does not exist
- verify: json_path(path="session_ids", matches=".+")
- code: `groom/groom/store.py::attend_get`

Used by the control CLI to look up the job context.

### method: attend_by_session
- sig: `(session_id: str) -> dict[str, Any] | None`
- does: scan every attendance and return the one whose `session_ids` list contains the given id
- verify: json_path(path="session_ids", matches=".*the session_id parameter passed to the method.*")
- returns: the converted row or `None` if no attendance contains the session id
- code: `groom/groom/store.py::attend_by_session`

The UI uses this lookup to navigate from a session id to its dispatch context.

This is a linear scan rather than an indexed lookup because the session_ids list is stored as JSON; a production deployment wanting subsecond latency on session lookup would denormalize this into a separate table.

### attend_orphans
- sig: `() -> list[dict[str, Any]]`
- consistency: attend-sessions-row — returns only rows where `status = ATTEND_RUNNING`, ordered oldest first by `started_at`, which is what boot recovery re-checks at startup to find attendants whose pid is stale
- returns: ordered list of converted rows
- code: `groom/groom/store.py::attend_orphans`
- verify: all(status=ATTEND_RUNNING)

Boot recovery calls this once on startup; a row that survived a groom restart is a run that was still held by an attendant when groom crashed, and recovery will respawn the attendant on the old code.

