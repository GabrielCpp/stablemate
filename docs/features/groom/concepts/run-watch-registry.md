---
type: concept
slug: run-watch-registry
title: Run watch registry
---
# Run watch registry

Run watch registry is groom's per-tab subscription map: which run's detail pane each connected browser tab currently has open. It is the addressing complement to the [dashboard client queue set](dashboard-client-queue-set.md) — the queue set is the fleet-wide fan-out, this map is how a message meant for one selection reaches only the tabs that asked for it.

The split exists because the two kinds of truth have different audiences. The fleet is a fleet-wide fact and every tab wants it, so it is broadcast. A run's detail is a consequence of *one operator's selection*; broadcasting it would send bandwidth proportional to tabs × open runs and have every tab discard almost all of it. Before this map the dashboard resolved that the other way, by having each tab poll `GET /worker/{id}/live` every five seconds; the subscription replaced the polling.

The map is keyed by the tab's outbound queue, not by a session id or a socket object, because the queue is already the thing a push has to be addressed to. That is also why the [dashboard websocket receive loop](dashboard-websocket-receive-loop.md) is handed its session queue: `watch` is the one command whose effect depends on which client spoke.

- code: groom/groom/state.py::WATCHING
- refs: [dashboard client queue set](dashboard-client-queue-set.md), [dashboard websocket receive loop](dashboard-websocket-receive-loop.md), [dashboard shell broadcaster](dashboard-shell-broadcaster.md), [groom projection module](groom-projection-module.md), [dashboard client store](dashboard-client-store.md)

## Contract

- scope: one in-memory dict per groom process, shared by the websocket command handler, the detail push path, and the live clock.
- key: the `asyncio.Queue` registered for one accepted dashboard websocket session — the same object held in the [dashboard client queue set](dashboard-client-queue-set.md).
- value: the container id of the run that tab has open, as a non-empty string.
- cardinality: at most one watched run per tab, and any number of tabs per run. A tab that selects a second run replaces its own entry; it does not accumulate subscriptions.
- unwatch: recording an empty run id removes the tab's entry rather than storing a falsey value, so "watching nothing" is the absence of a key and never a key mapped to `""`.
- disconnect: [unregister dashboard client](dashboard-client-queue-set.md#method-unregister-dashboard-client) pops the queue's entry as part of removing the client. Forgetting the subscription there rather than in the caller is what makes it impossible for a disconnect to leave a subscription pointing at a queue nobody reads — an entry that would otherwise survive for the life of the process.
- durability: purely process-local. A restarted server knows nothing about any tab's selection; the tab re-declares it on the next socket open, which is what makes reconnect self-healing.
- lifetime: starts empty at import, is mutated only through [record watch](#method-record-watch) and client removal, and is lost on process exit.
- concurrency: a plain dict mutated from one event loop; no lock, version, or transaction. Reads copy nothing beyond the comprehension each query builds.
- excluded: the map holds no query string, mode, scroll position, repository selection, or any other per-tab UI state. Those stay in the browser's [dashboard client store](dashboard-client-store.md) and never round-trip to the server.

## Callers

- subscription: the websocket command handler routes `{"cmd": "watch", "run_id": …}` to [record watch](#method-record-watch), then immediately projects and sends that run's detail back on the same queue — so a selection is answered without a fetch.
- addressed push: [dashboard shell broadcaster](dashboard-shell-broadcaster.md)'s detail push asks [watchers of run](#method-watchers-of-run) for the target queues and returns early when the list is empty, which is what keeps a run nobody is looking at from costing two SQLite reads on every state change.
- live clock: the live ticker asks [watched run ids](#method-watched-run-ids) for the set of runs it has to refresh, so the periodic detail work is proportional to what operators actually have open rather than to the size of the fleet.
- disconnect cleanup: [unregister dashboard client](dashboard-client-queue-set.md#method-unregister-dashboard-client).

## Fields

### field-watching-map

- type: `dict[asyncio.Queue, str]`
- default: empty dict at module import
- required: true
- code: groom/groom/state.py::WATCHING
- meaning: the current process-local subscription set — each connected tab that has a run open, mapped to that run's container id.

## Methods

### method-record-watch

- sig: `watch(queue: asyncio.Queue, run_id: str) -> None`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/state.py::watch

Record which run one tab has open, or forget its subscription entirely.

#### Inputs

- queue: the outbound queue of the tab that sent the command; required; default none.
- run_id: a container id, or the empty string to mean "this tab has nothing open"; required; default none.
- validation: the id is not checked against the [workflow registry](workflow-registry.md). A subscription to a run that does not exist simply never matches a push, and a run that appears later starts matching without a second command.

#### Effects

- Writes: sets `WATCHING[queue] = run_id` for a non-empty id, replacing any previous entry for that queue.
- Removes: pops the queue's entry for an empty id, tolerating an already-absent key.
- Does not: register or unregister the queue in the client set, project a payload, enqueue a message, send a websocket frame, read workflow state, or persist anything outside process memory.
- Bottoms out: built-in dict assignment and `pop`; no other first-party groom symbol is called.

### method-watchers-of-run

- sig: `watchers_of(run_id: str) -> list[asyncio.Queue]`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/state.py::watchers_of

#### Effects

- Reads: scans the map once and returns every queue whose recorded id equals the argument exactly; there is no prefix, short-handle, or case-insensitive match.
- Returns: a new list, so the caller may enqueue to it while further watch commands mutate the map.
- Empty result: an unwatched run yields an empty list, which callers treat as "skip the work entirely" rather than as an error.

### method-watched-run-ids

- sig: `watched_ids() -> set[str]`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/state.py::watched_ids

#### Effects

- Reads: collapses the map's values to a set, so a run five tabs have open is refreshed once and pushed to five queues.
- Returns: a new set; membership reflects the moment of the call.

## Algorithms

### algorithm-address-one-run-detail

- step: A tab selects a run and sends `{"cmd": "watch", "run_id": …}` on its socket.
- step: The command handler records the subscription against that tab's queue and pushes the run's current detail back on the same queue.
- step: On any later state change to that run, the detail push asks for the run's watchers and returns immediately if there are none.
- step: For each watcher queue, the projected `detail` message is enqueued directly — never through a fleet-wide broadcast pass.
- step: On disconnect, removing the client also drops its subscription, so the next push for that run does not address a dead queue.

## Failure Semantics

- No error surface of its own: every operation is a dict read or write that cannot fail for a well-formed queue and string.
- A push that fails to enqueue for one watcher does not unsubscribe it; the tab recovers its fleet view through the [dashboard resync poller](dashboard-resync-poller.md) and its detail through the re-`watch` sent on the next socket open.
- A stale entry is impossible to accumulate: the only way a queue is added is a live command on that queue, and the only ways it leaves are a replacement, an explicit unwatch, and client removal.
