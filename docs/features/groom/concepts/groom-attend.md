---
type: concept
slug: groom-attend
title: Attendant dispatch
---
# Attendant dispatch

When a run announces it is blocked on a gate or has died without reaching its own end, groom dispatches an attendant — an outside actor that can investigate, make a decision, and carry the run forward. The attendant contract is channel-agnostic: the same job can be claimed by an interactive session from a fleet-wide queue, or spawned as a headless Claude agent in the run's workspace.

- code: `groom/groom/attend.py`
- tests: `groom/tests/test_attend.py`

The module is called from `groom.app._poll_gate_soon` and the exit-alert pathway. Nothing here reaches upward to groom's own state — every dispatch is a fire-and-forget notification that drives a row in the `attend` table or publishes a job to the session queue.

## Modes and configuration

Three dispatch modes are configured in `[groom.attend]` of the home config, off by default:

- **`off`** — no dispatch. An unconfigured groom is exactly the dashboard it was before attendant support shipped.
- **`session`** — publish jobs to a fleet-wide queue at `GET /api/attend/queue`, for an interactive session to claim. No process is spawned and no row is written; what the attendant did is in the operator's terminal.
- **`headless`** — spawn a `claude -p` agent directly in the run's workspace. The job is passed on stdin and the attendant owns its own lifecycle: the row is written before the first byte of output (so a groom restart still knows what it spawned), and exit status is recorded in a daemon thread.

Settings are resolved from config first, then environment (`GROOM_ATTEND*` vars), then a documented default. The cache is invalidated by file mtime, so a dashboard toggle reloads the setting on the next announcement with no restart.

## Deny patterns and gatekeeping

Certain gates are not an attendant's to answer — a red PR that cannot be pushed is an infrastructure problem, not one the attendant clears by trying harder. The `deny` setting is a list of substrings; a dispatch checks both the gate path and the question text against the deny list (lowercased). A match vetos the dispatch. An empty list (the default) allows all operator-gated dispatches.

## Queue lifecycle

Outstanding jobs live in a module-scoped `_Ledger` that holds:
- `jobs`: job_id → `AttendJob`, the full set a session polls
- `by_run`: run_id → job_id, the dedupe that enforces one attendant per run

In `session` mode this is the whole dedupe; in `headless` mode it is the in-memory half, backed by the durable `attend` row that survives a groom restart.

Jobs are released (dropped from the ledger) when:
1. The gate clears and the run resumes
2. The run is running again
3. An attendant is stopped by the operator
4. An attendant exits and its row is finalized

A second dispatch for the same run is rejected — the blocked check calls `_blocked()`, which queries both the ledger and the store, so either dispatch mode's outstanding job prevents a second spawn.

## Job structure and dispatch entry points

### method: attend_gate
- sig: `(*, run_id: str, workflow: str, run_dir: str, workspace: str, gate_path: str, question: str, kind: str = ATTENDABLE_KIND, now: float | None = None, spawner: Spawner | None = None) -> AttendJob | None`
- does: reject if `kind != "operator"` (machine waits are not attendable)
- does: reject if `gate_path` or `question` contains a deny pattern
- does: reject if an attendant is already on this run
- does: dispatch an `AttendJob` with `kind = "gate"` and return it when no rejection fires
- returns: the job if dispatched, `None` if any reject clause fired
- code: `groom/groom/attend.py::attend_gate`
- detail: [attend job](../attend-job.md)
- verify: emitted(event="AttendJob", count=1)

### method: attend_death
- sig: `(*, run_id: str, workflow: str, run_dir: str, workspace: str, now: float | None = None, spawner: Spawner | None = None) -> AttendJob | None`
- does: reject if an attendant is already on this run
- does: read the failure handoff from `inbox.jsonl` in run_dir, returning machine-readable `failure_class` and `node`
- does: create an `AttendJob` with `kind = "death"` and the captured failure metadata
- does: dispatch the job and return it
- returns: the job if dispatched, `None` if rejected
- code: `groom/groom/attend.py::attend_death`
- detail: [attend job](../attend-job.md)
- verify: emitted(event="AttendJob", count=1)

### read_failure
- sig: `(run_dir: str) -> tuple[str, str, str]`
- does: read `inbox.jsonl`, find the last message with `kind = "failure"`, parse its body for `failure_class:` and `node:` fields
- returns: `(failure_class, node, body)` or `("", "", "")` if no failure message exists
- code: `groom/groom/attend.py::read_failure`

## Headless spawning

The headless dispatch spawns a Claude agent in the run's workspace and owns its lifecycle. The spawner contract is a callable `(job: AttendJob) -> None`.

### spawn_headless
- sig: `(job: AttendJob) -> None`
- does:
  - mint a session id (for claude CLI only; other CLIs get empty)
  - call `_launch(job, session_id)` to spawn `claude -p` through `ProcessSupervisor`
  - write a row to the `attend` table with `status = running` before the process runs
  - start a daemon thread that waits on the process, fetches its transcript if it ran, and finishes the row
- code: `groom/groom/attend.py::spawn_headless`
- detail: [reason method](../attend-job.md#reason)
- verify: persists(subject="attend table row", field="status", value="running")

The spawned prompt is the attendant doctrine (shipped in `groom/groom/prompts/attend-gate.md`) followed by the job's `.facts()` summary. The doctrine establishes the rules; the facts give context (run id, workspace, gate body or failure summary, etc.). The stdout is discarded (the session transcript is the record).

### stop
- sig: `(job_id: str) -> bool`
- does: if the row shows `status = running`, send `SIGTERM` then `SIGKILL` to the process group; fetch and store its transcript; mark the row `status = stopped`
- returns: `True` if a process was killed, `False` if the row doesn't exist or is not running
- errors: if `pid` is stale (process already dead), the second signal may fail — caught and logged, not raised
- code: `groom/groom/attend.py::stop`
- verify: persists(subject="attend table row", field="status", value="stopped")

### recover_orphans
- sig: `() -> int`
- does: 
  - scan every `attend` row with `status = running`
  - for each: if its pid is still alive, leave it (another groom or a long-lived attendant)
  - if the mode is `headless` and the pid is dead: mint a new session id, respawn the agent, append it to the session id list in the row, start a new ownership thread
  - if the mode is not `headless`: mark the row `status = lost`
- returns: count of attendants restarted
- code: `groom/groom/attend.py::recover_orphans`
- verify: persists(subject="attend table row", field="session_ids", value="appended")

Boot recovery is called from `groom.main` as groom starts up, one time. A row that survived a restart represents a run that was still held by an attendant when groom died, and the respawn continues the repair on the old code — the code the run is actually executing. Restarting without respawning would abandon the run with its checkpoint frozen.

## Queue and release

`queue` walks the module-scoped `_LEDGER.jobs`, orders every `AttendJob` by `created_at` (oldest first), and serialises each through `AttendJob.as_dict()`. In `session` mode the result is the fleet-wide view a session polls; in `headless` mode it backs the in-memory half of the dedupe, while the durable half lives in the `attend` table.

### queue
- sig: `() -> list[dict]`
- returns: ordered list of jobs
- code: `groom/groom/attend.py::queue`

This endpoint is polled by `GET /api/attend/queue` and rendered in the session pane of the dashboard. A session claims a job by calling the control CLI with the job's `run_id`.

### release
- sig: `(run_id: str) -> None`
- does: drop this run's job from the ledger (remove from `by_run` and `jobs`)
- code: `groom/groom/attend.py::release`

Called when a run is resumed, a gate is cleared, or an attendant is stopped.

### reset
- sig: `() -> None`
- does: clear both dicts in the ledger
- code: `groom/groom/attend.py::reset`

Used only in tests to isolate state between test cases.

## Spawner protocol

The `Spawner` type alias `Callable[[AttendJob], None]` abstracts how a job reaches an attendant. The default is `spawn_headless`; tests inject a mock spawner to avoid spawning real processes.

When `mode() == HEADLESS`, `_dispatch()` calls the spawner (defaulting to `spawn_headless`). In `SESSION` mode, the spawner is never called; the job is published to the ledger and polled by sessions.
