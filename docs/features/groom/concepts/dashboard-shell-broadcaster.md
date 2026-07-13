---
type: concept
slug: dashboard-shell-broadcaster
title: Dashboard shell broadcaster
---
# Dashboard shell broadcaster

Dashboard shell broadcaster is the shared groom server helper that turns the current [workflow registry](workflow-registry.md) snapshot into an out-of-band [dashboard shell fragment](../dashboard-shell-fragment.md) through the [dashboard shell renderer](dashboard-shell-renderer.md) and offers that fragment to every connected [websocket-dashboard](../http/groom.md#websocket-dashboard) client through the [dashboard client queue set](dashboard-client-queue-set.md). The [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet), [receive progress push](../http/groom.md#receive-progress-push), [receive exited push](../http/groom.md#receive-exited-push), [sidecar hello applier](sidecar-hello-applier.md), [sidecar progress applier](sidecar-progress-applier.md), and [startup background discovery scan](startup-background-discovery-scan.md) paths use it when they need dashboard tabs to converge on the current inbox and status-bar state without directly handling renderer or client-queue details.

- code: groom/groom/app.py::_broadcast_shell
- refs: [workflow registry](workflow-registry.md), [dashboard shell renderer](dashboard-shell-renderer.md), [dashboard shell fragment](../dashboard-shell-fragment.md), [dashboard client queue set](dashboard-client-queue-set.md), [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md)

## Contract

- sig: `async _broadcast_shell() -> None`
- purpose: produce one current dashboard shell fragment and enqueue it for all browser dashboard websocket clients currently registered with the groom process.
- input: none; the helper reads the process-local workflow registry through [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot) rather than accepting a caller-supplied workflow list, query string, client list, or transport object.
- output: no return value; completion means the rendered fragment has been accepted by the broadcast queueing layer for every dashboard client queue present in that broadcast pass.
- shell scope: includes the operator inbox/list region and status bar rendered as a [dashboard shell fragment](../dashboard-shell-fragment.md); it does not include selected worker detail, files, diff, repository picker, notification scripts, or answered-event scripts.
- client scope: targets only browser dashboard websocket clients registered in the process-local [dashboard client queue set](dashboard-client-queue-set.md); it does not send to sidecar websockets and does not create a websocket connection for absent clients.
- call graph: the helper calls exactly the local workflow snapshot helper, the [dashboard shell renderer](dashboard-shell-renderer.md#method-render-shell-data), and [broadcast dashboard fragment](dashboard-client-queue-set.md#method-broadcast-dashboard-fragment); it has no direct Docker, gate-file, HTTP-response, sidecar-RPC, or browser-session logic.
- snapshot consistency: the inbox/list and status-bar roots are rendered from the same workflow-list snapshot returned by [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot) for this broadcast pass.
- query rule: always uses the shell renderer's default empty query, so broadcasts show the full currently actionable inbox rather than preserving or applying one browser tab's search text.
- out-of-band mode: always renders with `oob=True`, so both shell roots are marked for htmx out-of-band replacement in already-loaded dashboard documents.
- call cardinality: each helper invocation renders exactly one shell fragment and performs exactly one dashboard-client broadcast call; it does not debounce, coalesce, retry, or schedule a later broadcast.
- empty-client rule: when no dashboard clients are registered, rendering still happens and the broadcast queue pass completes after enqueueing to zero queues.
- errors: renderer failures and broadcast-queue failures are not converted to helper-specific results; callers observe the raised exception and decide whether their state mutation has already happened.
- state: does not mutate workflow records, discovery flags, gate maps, answer logs, sidecar registrations, or Docker volumes.

## Callers

- refresh start: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) sets the discovery scanning flag, then calls this broadcaster so connected dashboard tabs can render the loading state before the reconciliation pass begins.
- refresh completion: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) clears the discovery scanning flag after reconciliation, then calls this broadcaster so tabs receive the pruned or refreshed fleet snapshot.
- progress push: [receive progress push](../http/groom.md#receive-progress-push) upserts one workflow as running, then calls this broadcaster so the inbox and status bar reflect the new current-node and state.
- exited push: [receive exited push](../http/groom.md#receive-exited-push) marks one workflow finished, records any accepted exit code, clears all open gates, then calls this broadcaster so stale actionable rows disappear and status counts update.
- sidecar hello: [sidecar hello applier](sidecar-hello-applier.md) rebuilds one connected workflow from a sidecar snapshot, then calls this broadcaster for the authoritative connected-container state.
- sidecar progress: [sidecar progress applier](sidecar-progress-applier.md) marks a connected workflow running, then calls this broadcaster for the live progress update.
- startup scan: [startup background discovery scan](startup-background-discovery-scan.md) clears the initial scanning flag after discovery reconciliation, then calls this broadcaster so already-connected dashboard tabs leave the loading state.
- excluded companion-script paths: blocked-gate pushes, sidecar blocked frames, and dashboard answer handling render the same [dashboard shell fragment](../dashboard-shell-fragment.md) but bypass this helper because they append a blocked-notification or answered-event script fragment to the same websocket payload.

## Inputs

### field: workflow-registry-snapshot

- type: `list[WorkflowContainer]`
- default: current values of the process-local [workflow registry](workflow-registry.md)
- required: true
- source: [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot)
- meaning: membership snapshot used by the shell renderer for both the inbox/list and status-bar portions of this broadcast.
- isolation: later workflow mutations do not change the already-rendered fragment for this broadcast pass.

### field: out-of-band-mode

- type: `bool`
- default: `True`
- required: true
- meaning: fixed renderer option that marks both produced dashboard shell roots with `hx-swap-oob="true"`.
- override: callers cannot request in-band shell rendering through this helper.

## Outputs

### field: enqueued-shell-fragment

- type: [dashboard shell fragment](../dashboard-shell-fragment.md)
- default: none
- required: true
- sink: [broadcast dashboard fragment](dashboard-client-queue-set.md#method-broadcast-dashboard-fragment)
- meaning: already-rendered HTML fragment offered to every dashboard client queue registered at broadcast time.
- transport envelope: sent as raw websocket text by downstream dashboard send loops, with no JSON wrapper, acknowledgement id, retry id, or delivery receipt added by this helper.

## Effects

- Reads the current [workflow registry](workflow-registry.md) values through the [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot) method.
- Calls the [dashboard shell renderer](dashboard-shell-renderer.md) with the current workflow list and out-of-band mode enabled.
- Renders one [dashboard shell fragment](../dashboard-shell-fragment.md) with out-of-band swap markers for the current workflow list.
- Broadcasts the rendered fragment through the process-local [dashboard client queue set](dashboard-client-queue-set.md#method-broadcast-dashboard-fragment).
- Preserves caller-specific payload additions: callers that need a blocked notification script or a `groom:answered` script build and broadcast their own fragment rather than using this helper.

## Methods

### method-broadcast-shell

- sig: `async _broadcast_shell() -> None`
- abstract: false
- raises: propagates exceptions from workflow snapshot creation, shell rendering, dashboard client queue snapshotting, or queue `put` calls; no helper-specific error value is returned.
- code: groom/groom/app.py::_broadcast_shell

Render and enqueue the current dashboard shell for browser dashboard websocket clients after a caller has already changed, or is about to expose, workflow fleet state.

#### Effects

- Reads: process-local workflow registry membership through [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot).
- Calls: [dashboard shell renderer](dashboard-shell-renderer.md#method-render-shell-data) once with the snapshot, default empty query, and `oob=True`.
- Calls: [broadcast dashboard fragment](dashboard-client-queue-set.md#method-broadcast-dashboard-fragment) once with the already-rendered shell string; all per-client queue snapshotting and queue writes belong to that downstream layer.
- Emits: one [dashboard shell fragment](../dashboard-shell-fragment.md) whose top-level roots target the dashboard inbox/list and status-bar regions.
- Preserves: workflow registry contents, individual workflow fields, gate maps, discovery scanning flag, answer log entries, sidecar websocket registrations, dashboard client membership, and Docker volume state.
- Excludes: selected worker detail, repository menu, files tree, file contents, diffs, blocked notification scripts, answered-event scripts, sidecar JSON frames, and HTTP response metadata.

## Algorithms

### algorithm-shell-broadcast

- step: Read the current workflow registry values into a new list through [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot).
- step: Pass that list to [dashboard shell renderer](dashboard-shell-renderer.md#method-render-shell-data) with out-of-band mode enabled and no inbox query override.
- step: Receive one [dashboard shell fragment](../dashboard-shell-fragment.md) containing the inbox/list replacement root followed by the status-bar replacement root.
- step: Offer the fragment to [broadcast dashboard fragment](dashboard-client-queue-set.md#method-broadcast-dashboard-fragment), which snapshots the registered dashboard client queues and awaits one enqueue per queue.
- step: Return only after every queue selected by that broadcast pass has accepted the fragment, or let the first rendering/enqueue exception propagate to the caller.

## Failure Semantics

- If workflow snapshot creation or [dashboard shell renderer](dashboard-shell-renderer.md#method-render-shell-data) raises, no broadcast queueing is attempted by this helper.
- If [broadcast dashboard fragment](dashboard-client-queue-set.md#method-broadcast-dashboard-fragment) raises after enqueueing to one or more queues, those earlier enqueues are not rolled back and later queues in the pass may not receive the fragment.
- The helper does not catch cancellation; an interrupted broadcast may leave caller-side workflow mutations visible in memory without a matching shell fragment having reached every registered dashboard tab.
- The helper has no retry, acknowledgement, persistence, or stale-client cleanup behavior; websocket session cleanup and outbound sending are owned by the [websocket-dashboard](../http/groom.md#websocket-dashboard) path.
