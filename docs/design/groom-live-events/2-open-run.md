# Slice 2: the open run follows events

Read [the design note](../groom-live-events.md) and [slice 1](1-fleet.md) first. This
slice needs slice 1 merged.

**When it lands:** the run an operator has open updates within a tenth of a second of
new telemetry or a new transcript line. A quiet open run sends no detail frames. Activity and
Raw fetch again only when the run produced something new. The 5-second live clock is
gone.

## Where things are today

- `groom/groom/app.py`:
  - `_push_detail(changed)` builds `projection.run_detail(...)` and sends a `detail`
    frame to each tab in `state.watchers_of(run)`.
  - `_live_loop`, `LIVE_TICK_S`, `_spawn_live` and `_stop_live` drive the clock.
  - `_push_watched()` runs `_tail_transcript` for native runs and rebuilds every watched
    detail every tick.
  - `_handle_command` handles `watch` and pushes one detail at once.
- `groom/groom/projection.py`. These take `now` and return values derived from it:
  `run_detail`, `head`, `metrics`, `history_lines`, `_turn_line` (a running turn's
  `duration = now - ts`), `running_node` and `running_strip`.
- `groom/groom/live_history.py`. `LiveHistory` buffers spans, logs and metrics for a
  watched run.
- `groom/groom/assets/dashboard.js`:
  - Activity polls `/activity` every 3 s (near lines 2557 to 2561).
  - Raw polls every `RAW_POLL_MS` (3 s, near lines 2562 to 2567).
  - `onDetail` (near line 3081) applies a `detail` frame.
- `groom/tests/test_app.py`. `test_the_clock_refreshes_every_open_pane_alongside_the_fleet`
  (near line 261) asserts the clock behaviour this slice removes.

## Steps

1. **Make the detail stable over time.** Enumerate every field of `run_detail(...)`
   whose value changes when only `now` changes. Build the detail for one run twice
   with `now` 10 s apart and diff the two. Turn each such field into a timestamp the
   client draws from. A running turn's `duration` becomes `started_ts` with
   `duration: null`. An elapsed figure becomes its start timestamp. The client renders
   these from the shared 1-second ticker that already drives `Elapsed`. Report any field
   you cannot convert as a design gap, and leave it as it is.
2. **Add the revisions to `LiveHistory`.** `activity_rev: int` rises on each span batch,
   log batch and transcript line batch. `metrics_rev: int` rises on each metric batch.
   `run_detail` copies both into the detail. A run with no `LiveHistory` sends 0.
3. **Add `live.mark_run(run_id)` and the detail flush to `groom/groom/live.py`.** The
   flush runs in the same coalescing pass as the fleet flush. For each dirty run with
   watchers, it builds the detail and compares it to the last detail sent for that run,
   ignoring `ts`. It sends the detail only when it differs. The last-sent map drops an
   entry when the run has no watcher left.
4. **Replace `_push_detail`.** Every caller calls `live.mark_run(id)` instead. The
   `watch` command clears the last-sent entry for the run, then marks it, so a newly
   opened pane always receives one detail. The slice 1 overflow callback marks the run.
5. **Tail native transcripts on file events.** When a tab starts watching a native run,
   start one task per run that runs `watchfiles.awatch` on the run's transcript
   directory, calls `_tail_transcript` on each change, bumps `activity_rev` when lines
   were read, and marks the run. `state._release_histories` cancels the task when the
   run loses its last watcher. Use the same `DefaultFilter` style as `sidecar.py`.
6. **Delete the clock.** Remove `_live_loop`, `LIVE_TICK_S`, `_spawn_live`, `_stop_live`,
   `_push_watched` and the `GROOM_LIVE_TICK_S` setting. Remove its line from
   `groom/README.md` and from any settings documentation `grep -rn GROOM_LIVE_TICK_S`
   finds.
7. **Update the browser client in `dashboard.js`:**
   - Delete the Activity and Raw `setInterval` polls and `RAW_POLL_MS`.
   - Activity refetches when the detail's `activity_rev` moves and the pane is open, with
     a 300 ms debounce.
   - Raw refetches on `activity_rev` or `metrics_rev`, whichever it shows, with the
     same debounce.
   - Draw the fields step 1 turned into timestamps from the shared ticker.
8. **Update the terminal client.** If `tui/` reads any field step 1 changed, draw it
   from the timestamp at render.
9. **Update the book.** Load the `ostler-book` skill. The endpoints and screens that
   described a refresh every few seconds now describe a refresh on change. Find them
   with `ostler book search refresh --service services.groom` and
   `ostler book search poll --service services.groom`. Add the revision fields to the
   detail record in `services/groom/model/records.py` if `ostler book check` asks. Add
   the decision `services/groom/web/decisions/the-open-run-follows-events-not-a-clock.md`.

## Tests

Add to `groom/tests/test_live.py`, with `GROOM_FLUSH_S=0.01`:

- A watched run with no ingest receives no `detail` frame over 0.5 s after the first.
- One log batch for a watched run raises `activity_rev` by one and sends one `detail`.
- Two log batches inside one flush window send one `detail`.
- A `watch` command sends a detail at once even if the same detail went out before.
- A native run's transcript file grows by one line, and a `detail` frame with a higher
  `activity_rev` arrives within 1 s. Use `tmp_path` for the run directory.
- Releasing the last watcher cancels the transcript task.
- `run_detail` built twice 10 s apart with no new data is equal, ignoring `ts`.

Replace `test_the_clock_refreshes_every_open_pane_alongside_the_fleet` with the test
that a quiet pane gets nothing. Delete any `_live_loop` test slice 1 kept.

Update `groom/tests/test_activity_follow_dynamic.py`: with the Activity pane open and no
ingest, no `/activity` request leaves the page over 5 s. After one ingest, one request
leaves within 1 s.

## Checks that close the slice

Run each from the repo root:

- `uv run pytest -n auto groom/tests` is green.
- `make lint` exits 0.
- `ostler book check services.groom --app .` passes.
- `ostler book run services.groom` is green.
- `grep -rn "LIVE_TICK_S\|_live_loop\|_push_watched\|RAW_POLL_MS" groom/` prints nothing.

The coordinator then has `e2e-web` open a running run's Activity tab, watch the network
panel stay quiet while the run is quiet, and see a new line arrive after an ingest.

Commit as `feat(groom): push the open run on events and drop the live clock`.
