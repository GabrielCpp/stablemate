# Slice 1: the fleet follows events

Read [the design note](../groom-live-events.md) first. This plan builds sections 3 and
4 of it for the run list, the status bar and the tab queues.

**When it lands:** the operator's run list changes within a tenth of a second of the
telemetry that changed it. A run turns silent at the moment its silence passes
`GROOM_LIVE_AFTER_S`. A quiet fleet sends only a heartbeat. A tab that stops reading costs
groom at most 256 queued frames.

## Where things are today

- `groom/groom/app.py`. `_broadcast_shell(changed)` (near line 106) sends
  `projection.state_message(...)` to every tab and, with `changed`, calls
  `_push_detail`. More than 15 call sites use it: the OTLP receivers through
  `_project_native_rows` and `_refresh_figures`, the sidecar socket handlers, the
  `/push/*` routes, `_answer`, `/refresh`, and the attend, settings and dispatch POSTs.
- `_live_loop` (near line 1730) runs every `LIVE_TICK_S` (5 s). It backfills gate paths
  over the control socket with `_backfill_wait_gate`, re-syncs every native row, then
  calls `_broadcast_shell()` and `_push_watched()`.
- `groom/groom/state.py`. `CLIENTS` holds one unbounded `asyncio.Queue` per tab.
  `broadcast` and `send` use `await queue.put`.
- `groom/groom/projection.py`. `state_message`, `fleet_rows`, `run_row`, `liveness`,
  `silence_of`, `started_at` and `row_clock`. `started_at` falls back to `now` when a
  gauge timestamp is missing, so `clock.since_ts` moves with the clock.
- `groom/groom/attend.py` `_own._wait` runs in a thread and calls
  `attend_ledger.attend_finish` and `release`. Nothing tells the tabs.
- `groom/groom/assets/dashboard.js`. `applyState` (near line 157) replaces `runs`.
  `applyRun` (near line 173) merges one row and re-sorts by `rank` and `name`. `onFrame`
  (near line 267) dispatches by `type`. `RunRow` (near line 511) draws `live_label`. A
  shared 1-second ticker (near line 773) already drives `Elapsed`.
- `groom/groom/tui/store.py` has `apply_state` and `apply_run`. `groom/groom/tui/app.py`
  `handle_frame` (near line 159) dispatches by `type`, and `set_interval(EVAL_EVERY_S,
  self.evaluate)` already runs a clock.

## Steps

1. **Create `groom/groom/live.py`.** It holds:
   - `bind(loop)`, called from a new `on_startup` hook, which keeps the event loop for
     thread-safe marks.
   - `mark_fleet()`, which sets a dirty flag and schedules one flush after
     `GROOM_FLUSH_S` (default 0.1) if none is scheduled.
   - `mark_fleet_threadsafe()`, which calls `mark_fleet` through
     `loop.call_soon_threadsafe`. It is a no-op before `bind`.
   - `flush_fleet()`. It returns at once when `state.CLIENTS` is empty. Otherwise it
     builds the rows with `projection.fleet_rows(all workflows)` and the meta with a new
     `projection.fleet_meta(...)`. It compares each row's stable content with the last
     one sent, keyed by `id`. It sends `{"type": "run", "v", "run"}` for a new or changed
     row, `{"type": "run_removed", "v", "id"}` for a gone row, and
     `{"type": "fleet_meta", "v", ...}` when the meta changed. Each frame takes the next
     `v`.
   - `snapshot()`, which returns `state_message(...)` with the current `v` and resets
     the last-sent rows and meta to what that snapshot holds.
   - `schedule_liveness(run)`. It keeps one `loop.call_at` handle per run id. The
     deadline is the run's last signal (the max that `silence_of` uses) plus
     `LIVE_AFTER_S` plus 0.5 s. When it fires, it calls `mark_fleet()`. It is replaced
     on each call, and cancelled when the run is terminal or evicted.
   - `STABLE_EXCLUDED = ("silence_s", "telemetry_age_s", "live_label")`, used to build a
     row's stable content.
2. **Fix `projection.started_at`.** Fall back to `tel.last_telemetry_ts` before `now`,
   so a row built twice with no new telemetry carries the same `clock`.
3. **Add `last_seen_ts` to `run_row`.** It is the same max of timestamps `silence_of`
   uses, or 0 with no telemetry.
4. **Split `state_message`.** Factor the non-row fields (`scanning`, `attention`,
   `status`, `store`, `attend`) into `projection.fleet_meta(workflows)`.
   `state_message` adds `type`, `ts`, `runs` and `v`. `GET /api/state` keeps its shape
   plus `v`.
5. **Bound the tab queues in `state.py`.** Create each `/ws` queue with `maxsize=256`.
   `broadcast` and `send` use `put_nowait`. On `QueueFull`, they empty that queue, put
   `live.snapshot()` in it and mark the queue's watched run dirty. Until slice 2 that
   means calling `_push_detail` through a callback that `app.py` registers. `state.py`
   must not import `app.py`.
6. **Replace the fleet half of `_broadcast_shell`.** Every call site whose purpose is the
   fleet calls `live.mark_fleet()` instead. A call site with `changed` also keeps
   `await _push_detail(changed)`. Slice 2 moves the detail. Delete `_broadcast_shell`
   when no caller is left. On connect, `/ws` sends `live.snapshot()` as its first frame.
7. **Arm liveness deadlines.** After each OTLP ingest, call `live.schedule_liveness` for
   every run the batch touched. `state.evict_runs` cancels the deadline.
8. **Move the gate backfill off the clock.** When a run enters an operator or machine
   wait with no `wait_gate_path`, start one `_backfill_wait_gate` task for it. On
   failure, retry after 5, 10, 20 and then every 60 s while the wait is still open and
   still has no path. On success, mark the fleet. Remove the backfill from `_live_loop`.
9. **Shrink `_live_loop`.** It keeps only `_push_watched()`, which slice 2 removes.
   The native row re-sync and `_broadcast_shell()` leave it. Native rows are already
   synced on ingest in `_project_native_rows`.
10. **Tell the tabs about attend thread changes.** Call `live.mark_fleet_threadsafe()`
    after `attend_ledger.attend_finish` in `attend._own._wait`, and after every other
    attend ledger write that runs off the event loop. Find them with
    `grep -n "attend_ledger\." groom/groom/*.py`.
11. **Update the browser client in `dashboard.js`:**
    - Keep `fleetV` in the store.
    - `state` replaces `runs` when `msg.v >= fleetV`.
    - `run` merges when `msg.v > fleetV`, then sets `fleetV`.
    - A new `run_removed` handler drops the row by `id`.
    - A new `fleet_meta` handler applies what `applyState` applies today minus `runs`,
      including the attend refetch on a moved `rev`.
    - `RunRow` draws `silent <duration since last_seen_ts>` from the shared ticker when
      `live === "dead"`, and `live_label` otherwise.
    - The HTTP resync path keeps using `applyState`.
12. **Update the terminal client.** `tui/store.py` gains `apply_remove` and
    `apply_meta`, and `tui/app.py` `handle_frame` routes the two new frames. The row
    label for a dead run is computed from `last_seen_ts` at render, and the existing
    `evaluate` interval re-renders those labels once a second.
13. **Update the README.** Rewrite the "How it works" paragraph about `GROOM_LIVE_TICK_S`
    in `groom/README.md` to describe deadlines and client-drawn labels. Remove the
    `GROOM_LIVE_TICK_S` mention once the setting is gone in slice 2. Until then, say it
    drives only the open run.
14. **Update the book.** Load the `ostler-book` skill. Add `last_seen_ts: float = 0.0`
    to `Row` in `services/groom/model/records.py` and `v` to the state record if
    `ostler book check` asks. Add a decision under `services/groom/web/decisions/`
    named `the-run-list-follows-events-not-a-clock.md`, in the format of its siblings.

## Tests

Add `groom/tests/test_live.py`. Use the queue-driving style of `test_app.py`
(`state.add_client(asyncio.Queue())`, `asyncio.run(drive())`), with
`GROOM_FLUSH_S=0.01`:

- A connected tab with no ingest receives no frame over 0.5 s.
- One metric batch for a known run sends exactly one `run` frame for that run, and no
  other `run` frame.
- Two batches inside one flush window send one `run` frame.
- With `GROOM_LIVE_AFTER_S=0.2`, an ingest and then 1 s of nothing yields a `run` frame
  whose `live` is `dead`.
- A row built twice 10 s apart (`now` passed in) has the same stable content.
- Removing a workflow sends `run_removed`.
- A full queue of 256 receives `state` as its next frame after the overflow.
- `mark_fleet_threadsafe` from a `threading.Thread` produces a `fleet_meta` frame.
- The gate backfill retries on failure and marks the fleet on success.

Rewrite or delete the `_live_loop` tests in `test_app.py` (`test_live_loop_*`,
`test_live_loop_backfills_incomplete_gates_before_syncing_rows`) to match step 9. Keep
`test_api_state_is_the_resync_payload` and
`test_api_state_and_the_socket_push_the_same_payload`, updated for `v`. Update the TUI
tests that feed frames (`test_tui_*.py`) for the two new frames.

## Checks that close the slice

Run each from the repo root:

- `uv run pytest -n auto groom/tests` is green.
- `make lint` exits 0.
- `ostler book check services.groom --app .` passes.
- `ostler book run services.groom` is green.
- `node --check` passes on `dashboard.js` (`test_dashboard_client.py` runs it).

The coordinator then has `e2e-web` walk the running app: push a run with
`POST /push/progress`, see the row appear, leave the page idle for 30 s with the socket
inspected in the network panel and see no frame, then stop the run's telemetry and see
the row turn silent and count up.

## Out of scope

The detail push on a clock, the Activity and Raw polls, Dispatch, History, Diff and
Files belong to slices 2 to 4.

Commit under the `stablemate-commit` skill as `feat(groom): push the fleet on events
instead of a clock`.
