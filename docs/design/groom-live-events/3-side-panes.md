# Slice 3: Dispatch and History follow events

Read [the design note](../groom-live-events.md) and [slice 1](1-fleet.md) first. This
slice needs slice 1 merged. It does not need slice 2.

**When it lands:** the Dispatch pane shows a queued run starting or finishing within a
tenth of a second. The History pane shows a new summary as soon as groom writes it.
Neither pane polls.

## Where things are today

- `groom/groom/dispatch.py` writes the dispatch ledger through `dispatch_ledger` on
  enqueue, start, stop and delete. `_own._wait` runs in a thread and calls
  `dispatch_ledger.dispatch_finish` and `_drain`. No write tells the tabs.
- `groom/groom/app.py`:
  - `_write_summary` writes a live run's summary and sends a `summary` frame.
  - `_summary_pass` calls `history.compute_archive` for archived runs and sends
    nothing.
- `groom/groom/assets/dashboard.js`:
  - The Dispatch pane polls every 5 s (near lines 3679 to 3688).
  - The History pane polls every 4 s while `totals.reading > 0 || unlisted > 0` (near
    line 3721).
- `groom/groom/tui/screens/dispatch.py` (near line 72) polls with
  `set_interval(POLL_S)`.

## Steps

1. **Add the revisions to the fleet meta.** `groom/groom/live.py` keeps
   `revs = {"dispatch": 0, "history": 0}`. `live.bump(name)` raises one and marks the
   fleet. `live.bump_threadsafe(name)` does the same through `call_soon_threadsafe`.
   `projection.fleet_meta` includes `revs`, so `fleet_meta` and `state` frames carry
   them.
2. **Bump `dispatch`.** Call `live.bump("dispatch")` after each dispatch ledger write on
   the event loop. Call `live.bump_threadsafe("dispatch")` after each write in a thread,
   including `_own._wait` and `_drain`. List every write with
   `grep -n "dispatch_ledger\." groom/groom/*.py` and cover each one.
3. **Bump `history`.** Call `live.bump("history")` at the end of `_write_summary` and
   after `history.compute_archive` returns in `_summary_pass` when it wrote anything.
4. **Update the browser client in `dashboard.js`:**
   - Delete the Dispatch `setInterval` and the History poll.
   - Each pane keeps the last `revs` value it fetched at.
   - Each pane refetches with a 300 ms debounce when the store's `revs` value moves and
     the pane is open.
   - Opening a pane fetches once, as today.
5. **Update the terminal client.** `tui/store.py` keeps `revs` from `state` and
   `fleet_meta`. `tui/screens/dispatch.py` drops `set_interval(POLL_S)` and reloads when
   `revs.dispatch` moves. Remove `POLL_S` if nothing else uses it.
6. **Update the book.** Load the `ostler-book` skill. Change the Dispatch and History
   screen pages that describe a poll. Add `revs` to the state record in
   `services/groom/model/records.py` if `ostler book check` asks. Add one line to the
   slice 1 decision `the-run-list-follows-events-not-a-clock.md` saying the side panes
   follow revisions carried by `fleet_meta`.

## Tests

Add to `groom/tests/test_live.py`, with `GROOM_FLUSH_S=0.01`:

- A dispatch enqueue sends one `fleet_meta` with `revs.dispatch` one higher.
- A dispatch finish from a `threading.Thread` sends a `fleet_meta` with a higher
  `revs.dispatch`.
- `_write_summary` sends a `fleet_meta` with a higher `revs.history`.
- `_summary_pass` with one run to archive sends a `fleet_meta` with a higher
  `revs.history`. With nothing to archive, it sends none.

Add a dynamic Playwright test in `groom/tests/` in the style of
`test_activity_follow_dynamic.py`. Open Dispatch, see no request to the dispatch list
endpoint over 6 s, enqueue a run over HTTP, and see the row appear within 1 s.

Update the terminal-client dispatch tests for the dropped interval.

## Checks that close the slice

Run each from the repo root:

- `uv run pytest -n auto groom/tests` is green.
- `make lint` exits 0.
- `ostler book check services.groom --app .` passes.
- `ostler book run services.groom` is green.

The coordinator then has `e2e-web` open Dispatch in a running groom, enqueue one run and
see its status move from queued to running to done with no fetch between changes.

Commit as `feat(groom): refresh dispatch and history on revision changes`.
