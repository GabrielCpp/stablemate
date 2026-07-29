---
type: concept
slug: dashboard-shell-broadcaster
title: Dashboard shell broadcaster
---
# Dashboard shell broadcaster

Dashboard shell broadcaster is the shared groom server helper that turns the current [workflow registry](workflow-registry.md) snapshot into a [dashboard state payload](../dashboard-state-payload.md) through the [groom projection module](groom-projection-module.md) and offers that payload to every connected [websocket-dashboard](../http/groom.md#websocket-dashboard) client through the [dashboard client queue set](dashboard-client-queue-set.md). When the caller names the one run that changed, it also pushes that run's detail payload to the tabs that declared themselves watchers in the [run watch registry](run-watch-registry.md) — both halves of a state change travel together, because a gate opening changes the row *and* the pane the operator has open. The [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet), [receive progress push](../http/groom.md#receive-progress-push), [receive blocked push](../http/groom.md#receive-blocked-push), [receive exited push](../http/groom.md#receive-exited-push), [sidecar hello applier](sidecar-hello-applier.md), [sidecar progress applier](sidecar-progress-applier.md), [sidecar blocked applier](sidecar-blocked-applier.md), and [startup background discovery scan](startup-background-discovery-scan.md) paths use it when they need dashboard tabs to converge on the current fleet and status-bar state without directly handling projection or client-queue details.

- code: groom/groom/app.py::_broadcast_shell
- refs: [workflow registry](workflow-registry.md), [groom projection module](groom-projection-module.md), [dashboard state payload](../dashboard-state-payload.md), [dashboard client queue set](dashboard-client-queue-set.md), [run watch registry](run-watch-registry.md), [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md)

## Contract

- sig: `async _broadcast_shell(changed: str = "") -> None`
- purpose: produce one current dashboard state payload, enqueue it for all browser dashboard websocket clients registered with the groom process, and — when a single run is what changed — enqueue that run's detail payload for the tabs watching it.
- input: an optional container id naming the run that changed; the fleet half reads the process-local workflow registry through [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot) rather than accepting a caller-supplied workflow list, query string, client list, or transport object.
- output: no return value; completion means the projected payload has been accepted by the broadcast queueing layer for every dashboard client queue present in that broadcast pass, and any watcher push has been enqueued.
- fleet scope: the state payload carries the run list and the status-bar counts as a single JSON object; it does not carry selected run detail, files, diff, repository picker contents, traces, or toasts.
- detail scope: the optional second half carries one run's detail slices — head, gates, metrics, log trail — addressed only to the queues watching that run.
- client scope: the fleet half targets only browser dashboard websocket clients registered in the process-local [dashboard client queue set](dashboard-client-queue-set.md); it does not send to sidecar websockets and does not create a websocket connection for absent clients.
- call graph: the helper calls exactly the local workflow snapshot helper, [state message](groom-projection-module.md#method-state-message), [broadcast dashboard message](dashboard-client-queue-set.md#method-broadcast-dashboard-message), and — for a named change — the run-detail push; it has no direct Docker, gate-file, HTTP-response, sidecar-RPC, or browser-session logic.
- snapshot consistency: the run list and the status-bar counts are projected from the same workflow-list snapshot returned by [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot) for this broadcast pass.
- query rule: always uses the projection's default empty query, so broadcasts show the whole fleet rather than preserving or applying one browser tab's search text. Filtering is a per-tab concern the client applies to the pushed list.
- transport rule: the payload is a `dict`, not a string. Serialization to JSON text belongs to the [dashboard websocket send loop](dashboard-websocket-send-loop.md), so nothing in this helper knows what a tab will do with a `state` frame.
- call cardinality: each helper invocation projects exactly one state payload and performs exactly one dashboard-client broadcast call, plus at most one watcher push pass; it does not debounce, coalesce, retry, or schedule a later broadcast.
- empty-client rule: when no dashboard clients are registered, projection still happens and the broadcast queue pass completes after enqueueing to zero queues.
- empty-watcher rule: when `changed` names a run no tab has open, the detail half returns before reading telemetry or logs — the two SQLite reads are only paid for when somebody is looking.
- errors: projection failures and broadcast-queue failures are not converted to helper-specific results; callers observe the raised exception and decide whether their state mutation has already happened.
- state: does not mutate workflow records, discovery flags, gate maps, answer logs, sidecar registrations, watch subscriptions, or Docker volumes.

## Callers

- refresh start: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) sets the discovery scanning flag, then calls this broadcaster so connected dashboard tabs can render the loading state before the reconciliation pass begins.
- refresh completion: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) clears the discovery scanning flag after reconciliation, then calls this broadcaster so tabs receive the pruned or refreshed fleet snapshot.
- progress push: [receive progress push](../http/groom.md#receive-progress-push) upserts one workflow as running, then calls this broadcaster with that container id so the fleet, the status bar, and any open pane for that run reflect the new current-node and state.
- blocked push: [receive blocked push](../http/groom.md#receive-blocked-push) records the new gate, then calls this broadcaster with that container id and separately broadcasts a `notify` message; the gate reaches the open pane through the detail half rather than through an appended script.
- exited push: [receive exited push](../http/groom.md#receive-exited-push) marks one workflow finished, records any accepted exit code, clears all open gates, then calls this broadcaster so stale actionable rows disappear and status counts update.
- sidecar hello: [sidecar hello applier](sidecar-hello-applier.md) rebuilds one connected workflow from a sidecar snapshot, then calls this broadcaster for the authoritative connected-container state.
- sidecar progress: [sidecar progress applier](sidecar-progress-applier.md) marks a connected workflow running, then calls this broadcaster for the live progress update.
- sidecar blocked: [sidecar blocked applier](sidecar-blocked-applier.md) records the gate a connected container advertised, then calls this broadcaster with that container id.
- answer handling: the dashboard socket's answer command calls this broadcaster with the answered container id, so the row and the open pane both converge before the `answered` confirmation frame is broadcast.
- startup scan: [startup background discovery scan](startup-background-discovery-scan.md) clears the initial scanning flag after discovery reconciliation, then calls this broadcaster so already-connected dashboard tabs leave the loading state.
- live clock: the live loop broadcasts the fleet on its own tick and refreshes every watched run, because `in node 12m` and the log trail are derived from `now` and a merely-running run emits no state change to push.

## Inputs

### field: workflow-registry-snapshot

- type: `list[WorkflowContainer]`
- default: current values of the process-local [workflow registry](workflow-registry.md)
- required: true
- source: [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot)
- meaning: membership snapshot used by the projection for both the run list and the status-bar portions of this broadcast.
- isolation: later workflow mutations do not change the already-projected payload for this broadcast pass.

### field: changed-container-id

- type: `str`
- default: `""`
- required: false
- meaning: the one run whose detail should also be pushed to its watchers. Empty means the caller changed something fleet-wide (or nothing run-specific) and only the state payload is sent.
- override: callers cannot ask for a detail push to tabs that did not subscribe; the watch registry, not the caller, decides who receives it.

## Outputs

### field: enqueued-state-payload

- type: [dashboard state payload](../dashboard-state-payload.md)
- default: none
- required: true
- sink: [broadcast dashboard message](dashboard-client-queue-set.md#method-broadcast-dashboard-message)
- meaning: already-projected JSON object offered to every dashboard client queue registered at broadcast time.
- transport envelope: enqueued as a `dict` and serialized to websocket text by the downstream dashboard send loop, with no acknowledgement id, retry id, or delivery receipt added by this helper. The same object shape is what [get-api-state](../http/groom.md#get-dashboard-state) returns, so a push and a resync land the tab in the same place.

### field: enqueued-detail-payload

- type: `dict` with `type: "detail"`, the run id, and the run's detail slices
- default: none when `changed` is empty or unwatched
- required: false
- sink: the queues returned by [watchers of](run-watch-registry.md#method-watchers-of-run)
- meaning: the same body [get-worker-detail](../http/groom.md#get-run-detail) returns, addressed to the tabs that have that run open.

## Effects

- Reads the current [workflow registry](workflow-registry.md) values through the [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot) method.
- Calls the [groom projection module](groom-projection-module.md) with the current workflow list and the default empty query.
- Broadcasts the projected payload through the process-local [dashboard client queue set](dashboard-client-queue-set.md#method-broadcast-dashboard-message).
- When `changed` is non-empty, reads that run's telemetry and log trail and enqueues one detail payload per watching queue.
- Preserves caller-specific messages: callers that need a blocked notification or an answered confirmation broadcast their own one-shot `notify`/`answered` message beside this call, so those events accompany a real change rather than every reconciliation re-push.

## Methods

### method-broadcast-shell

- sig: `async _broadcast_shell(changed: str = "") -> None`
- abstract: false
- raises: propagates exceptions from workflow snapshot creation, projection, dashboard client queue snapshotting, or queue `put` calls; no helper-specific error value is returned.
- code: groom/groom/app.py::_broadcast_shell

Project and enqueue the current dashboard state for browser dashboard websocket clients after a caller has already changed, or is about to expose, workflow fleet state — and refresh the open pane for whoever is watching the run that changed.

#### Effects

- Reads: process-local workflow registry membership through [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot).
- Calls: [state message](groom-projection-module.md#method-state-message) once with the snapshot and the default empty query.
- Calls: [broadcast dashboard message](dashboard-client-queue-set.md#method-broadcast-dashboard-message) once with the already-projected payload; all per-client queue snapshotting and queue writes belong to that downstream layer.
- Calls: the run-detail push once when `changed` is non-empty.
- Emits: one [dashboard state payload](../dashboard-state-payload.md) and, conditionally, one detail payload per watching queue.
- Preserves: workflow registry contents, individual workflow fields, gate maps, discovery scanning flag, answer log entries, sidecar websocket registrations, dashboard client membership, watch subscriptions, and Docker volume state.
- Excludes: repository menu, files tree, file contents, diffs, traces, notification messages, answered confirmations, sidecar JSON frames, and HTTP response metadata.

### method-push-detail

- sig: `async _push_detail(container_id: str) -> None`
- abstract: false
- raises: propagates exceptions from telemetry reads, projection, or queue `put` calls.
- code: groom/groom/app.py::_push_detail
- step: Look up the queues watching `container_id` through [watchers of](run-watch-registry.md#method-watchers-of-run).
- step: Return immediately when the list is empty, before any telemetry or log read.
- step: Look up the workflow in the registry and return when it is gone.
- step: Project the run's detail payload through [detail message](groom-projection-module.md#method-detail-message).
- step: Enqueue that one payload for each watching queue.

### method-push-watched

- sig: `async _push_watched() -> None`
- abstract: false
- raises: propagates exceptions from the per-run detail push.
- code: groom/groom/app.py::_push_watched
- step: Read the set of run ids some tab currently has open through [watched ids](run-watch-registry.md#method-watched-run-ids).
- step: Push each one's detail to its watchers, so clock-derived text in an open pane stays true for a run that emitted no state change.

## Algorithms

### algorithm-shell-broadcast

- step: Read the current workflow registry values into a new list through [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot).
- step: Pass that list to [state message](groom-projection-module.md#method-state-message) with no query override.
- step: Receive one [dashboard state payload](../dashboard-state-payload.md) carrying the ordered run list, the fleet-wide status counts, and the discovery scanning flag.
- step: Offer the payload to [broadcast dashboard message](dashboard-client-queue-set.md#method-broadcast-dashboard-message), which snapshots the registered dashboard client queues and awaits one enqueue per queue.
- step: If `changed` is empty, return.
- step: Otherwise push that run's detail to its watchers, or return early when nobody is watching it.

## Failure Semantics

- If workflow snapshot creation or [state message](groom-projection-module.md#method-state-message) raises, no broadcast queueing is attempted by this helper.
- If [broadcast dashboard message](dashboard-client-queue-set.md#method-broadcast-dashboard-message) raises after enqueueing to one or more queues, those earlier enqueues are not rolled back and later queues in the pass may not receive the payload.
- If the fleet half succeeds and the detail half raises, connected tabs have the new row but the watching tabs' panes are a tick behind until the next live tick refreshes them.
- The helper does not catch cancellation; an interrupted broadcast may leave caller-side workflow mutations visible in memory without a matching state payload having reached every registered dashboard tab.
- The helper has no retry, acknowledgement, persistence, or stale-client cleanup behavior; websocket session cleanup and outbound sending are owned by the [websocket-dashboard](../http/groom.md#websocket-dashboard) path. A tab that missed a push recovers on its own through the [dashboard resync poller](dashboard-resync-poller.md) rather than through anything this helper does.
