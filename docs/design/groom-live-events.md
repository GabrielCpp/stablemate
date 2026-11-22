# groom on events

## 1. Problem

An operator who leaves groom open is served by clocks, not by what happens. The server
rebuilds the whole run list and the open run every 5 seconds and pushes both to every
tab, whether anything changed or not. Four panes poll on their own timers. Activity and
Raw refetch every 3 seconds, Dispatch every 5 and History every 4. Diff and Files never
refresh until the operator presses Retry. The attendant and dispatch threads write their
ledgers and tell nobody, so their changes reach a tab only on the next tick or poll.

The cost shows in three ways:

- A change reaches the screen up to 5 seconds late, and a Diff never does.
- An idle dashboard still makes groom work. Every 5 seconds groom reads SQLite, renders
  the full fleet and reads transcripts on disk for each open run.
- A tab that stops reading grows groom's memory without limit, because every tab has an
  unbounded send queue.

**Done**, as the operator sees it: every pane changes the moment groom learns something.
A run turns silent at the moment its silence passes the liveness threshold, not at the
next tick. Diff and Files follow the run's workspace. A dashboard left open on a quiet
fleet receives only a heartbeat. Nothing an operator reads depends on a poll.

## 2. What stays

- **The tick for absence stays, as deadlines.** A run that stops emitting sends no
  event. groom keeps one timer per run that fires when its silence would cross the
  liveness threshold. The sweep over every run on a fixed clock goes away.
- **The client draws labels that count time.** The server sends the moment a thing
  began. The browser's 1-second ticker and the terminal client's clock turn it into
  "silent 4m" or "in node 12m". The fleet row already carries `clock.since_ts` for this.
  `last_seen_ts` joins it.
- **Snapshots stay the unit of resync.** A tab that connects, reconnects or falls behind
  gets one fresh snapshot. groom keeps no replay buffer for `/ws`. The snapshot is small,
  and a replay buys only bandwidth on loopback.
- **groom still sends the open run whole.** A detail frame goes out when the detail
  changed, not on a clock. Patching inside the detail is not worth its client code.
- **Housekeeping keeps its clocks.** Archive, prune, turn harvest, run summaries and the
  `/feed` digest are not dashboard freshness. The digest is periodic on purpose, because
  silence is not success.
- **Alert rules keep their 60-second check.** STALL, STUCK and WAITING fire after 30 to
  90 minutes. Firing up to a minute late does not change what the operator does.
- **HTTP reads keep their shapes.** `GET /api/state` still returns the full fleet. It
  gains `v`, and each row gains `last_seen_ts`. Every other field keeps its meaning.

## 3. The parts

| Part | Owns | Never knows |
| --- | --- | --- |
| `groom.live` (new) | Dirty marks, the coalescing flush, liveness deadlines, the last frame sent per topic, thread-safe marks from worker threads | Where a change came from, or how a pane draws |
| Sources: OTLP receivers, sidecar socket, POST handlers, attend and dispatch threads | Mutating `state` and calling `live.mark_*` | Which tabs are open |
| `projection` | Building a row, the fleet meta and a run detail from state | When to send |
| `state` | The client queues, bounded, with a snapshot on overflow | What a frame means |
| Browser and terminal clients | Applying a snapshot and a row change, drawing elapsed labels from timestamps, refetching a pane when its revision moves | Why a frame was sent |

A source never calls `state.broadcast` for the fleet or `_push_detail` for a run. It
marks what it touched. `groom.live` flushes the marks at most every `GROOM_FLUSH_S`
(0.1 seconds). The flush works out what changed and sends only that.

## 4. The protocol on `/ws`

Server to client:

| Frame | When | Body |
| --- | --- | --- |
| `state` | On connect, after an overflow, and as the body of `GET /api/state` | The full fleet, as today, plus `v` |
| `run` | A row's stable content changed | `v` and the row, as today |
| `run_removed` | A row left the fleet | `v` and `id` |
| `fleet_meta` | The status bar, attention list, store health, scanning flag, attendant summary or a pane revision changed | `v` and those fields |
| `detail` | The watched run's detail changed | As today, plus `activity_rev`, `metrics_rev` and `workspace_rev` |
| `notify`, `answered`, `answer_rejected`, `summary` | As today | As today |

`v` counts the fleet's frames and only goes up. A client ignores a `run`, `run_removed`
or `fleet_meta` whose `v` is not above the last one it applied. It ignores a `state`
whose `v` is below it. That settles the race between an HTTP resync and the socket.

A row's stable content is the row without `silence_s`, `telemetry_age_s`,
`live_label` and `last_seen_ts`. The flush compares that content to what it last sent.
A clock moving forward therefore sends nothing, and neither does a heartbeat from a live
run. A liveness class moving from `live` to `dead` changes `live`, so it does send, and
that frame carries the `last_seen_ts` the clients count from.

The meta compares the same way. Its `store` member leaves out `last_ok_ts`,
`last_write_ts`, `last_prune_ts` and `wal_bytes`, which move on every SQLite write. No
client draws them from the socket, and `GET /api/state` still returns them fresh. A
frame that does go out carries the whole row or the whole meta.

Client to server is unchanged: `watch` and the answer form.

## 5. Revisions instead of polls

Some panes are too large or too varied to push whole. Each of them follows a revision.
groom bumps the revision when the pane's source changes. The client refetches the pane
over the HTTP route it already uses, at most once per 300 milliseconds, while the pane
is open.

| Revision | Carried by | Bumped by | Pane that refetches |
| --- | --- | --- | --- |
| `activity_rev` | `detail` | A committed span or log batch for the run, a transcript line read | Activity, Raw |
| `metrics_rev` | `detail` | A committed metric batch for the run | Raw, when metric samples are shown |
| `workspace_rev` | `detail` | A `workspace` frame from the run's sidecar | Diff, Files |
| `revs.dispatch` | `fleet_meta` | Any dispatch ledger write | Dispatch |
| `revs.history` | `fleet_meta` | A summary written, live or archived | History |
| `attend.rev` | `fleet_meta` | Any attend ledger write | Attendant, as today |

## 6. Slices

Each slice lands working and deletes the clock or poll it replaces. Each has its own
plan beside this note.

1. [The fleet follows events](groom-live-events/1-fleet.md). The run list and status
   bar change on events and on liveness deadlines. The 5-second fleet push goes. Tab
   queues are bounded.
2. [The open run follows events](groom-live-events/2-open-run.md). groom sends the
   detail when it changes. Activity and Raw follow `activity_rev`. groom watches the
   native transcript instead of re-reading it. The 5-second loop goes.
3. [Side panes follow events](groom-live-events/3-side-panes.md). Dispatch and History
   follow their revisions. Their polls go, in the browser and in the terminal client.
4. [Diff and Files follow the workspace](groom-live-events/4-workspace.md). The sidecar
   reports workspace changes, and the open Diff and Files refetch.

Slice 1 comes first because the others build on `groom.live`. Slices 2, 3 and 4 touch
different panes. They share `groom/live.py`, `app.py` and `dashboard.js`, so they land
one after another, not in parallel.

## 7. Relation to other notes

[groom in the terminal](groom-tui.md) decided that the terminal client adds no frame
type. This note adds `run_removed` and `fleet_meta`, and the terminal client moves with
each slice. That decision still holds for the terminal client's own features.

## 8. Decisions

- **The flush diffs projections.** It does not trust each event to know which rows it
  touched. A source marks the fleet dirty. The flush recomputes every row and sends the
  ones whose stable content changed. A fleet holds tens of rows, so the recompute costs
  less than one missed patch.
- **`/ws` has no replay buffer.** A reconnecting tab gets a snapshot. `/feed` keeps its
  own replay, because a program reading it must not miss an event.
- **Overflow sends a snapshot.** A tab queue holds 256 frames. groom empties a full
  queue, puts one `state` frame in it and marks the tab's watched run dirty.
- **Alert rules stay on their minute clock.** Section 2 gives the reason.
- **Detail frames stay whole.** Section 2 gives the reason.
- **A quiet socket carries a heartbeat.** groom sends `{"type": "ping"}` to every tab
  every 5 s. Both clients mark a socket stale after 15 s with no frame, and an operator
  must not trust a frozen page. Without a frame, an idle fleet would read stale and
  trigger the HTTP resync every 5 s. The heartbeat replaces that poll with one small
  frame and keeps the stale chip true for a half-open socket.
