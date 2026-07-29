---
type: concept
slug: sidecar-blocked-applier
title: Sidecar blocked applier
---
# Sidecar blocked applier

The sidecar blocked applier is the groom server layer that folds a connected sidecar's live `blocked` [sidecar websocket frame](../sidecar-websocket-frame.md) into the process-local [workflow registry](workflow-registry.md) during the [run sidecar websocket session](../http/groom.md#run-sidecar-websocket-session) invocation. It requires a non-empty gate file path, marks the connected [workflow container](workflow-container.md) as [workflow state](workflow-state.md) `BLOCKED`, creates or replaces one [gate info](gate-info.md) record for that file path, broadcasts the fleet's current [dashboard state payload](../dashboard-state-payload.md) plus that run's refreshed detail through the [dashboard shell broadcaster](dashboard-shell-broadcaster.md#method-broadcast-shell), and then sends one separate [dashboard notify message](../dashboard-notify-message.md) built with the [question notification limit](groom-app-module.md#field-question-notify-limit) to every dashboard browser client through the [dashboard client queue set](dashboard-client-queue-set.md#method-broadcast-dashboard-message). It is the websocket delta counterpart of the HTTP [blocked push payload](../blocked-push-payload.md): both apply one gate-file delta, replace only that gate key, and keep unrelated open gates visible.

- code: groom/groom/app.py::_apply_socket_blocked

## Contract

- sig: `async _apply_socket_blocked(container_id: str, data: dict) -> None`
- precondition: [run sidecar websocket session](../http/groom.md#run-sidecar-websocket-session) has already accepted a useful `hello`, registered a [sidecar connection](sidecar-connection.md), and selected this layer only for a decoded object whose top-level `type` is `"blocked"`.
- input: `container_id` is the non-empty, already-normalized workflow container id held on the registered sidecar connection; this layer uses it exactly as supplied and does not read any container id from the blocked frame.
- input: `data` is the decoded sidecar `blocked` frame object; the layer reads only `file_path` and `question`, ignores every other field, and does not inspect the frame `type` because dispatch has already selected the blocked path.
- file-path rule: `file_path` is read as `str(data.get("file_path", ""))`; an absent key becomes `""`, JSON `null` becomes `"None"`, and an empty normalized path stops the layer with no registry mutation, gate creation, rendering, notification script, broadcast, acknowledgement frame, or error result.
- file-path scope: the file path is used exactly as the sidecar reported it; this layer does not canonicalize the path, check whether it is workspace-relative, inspect the filesystem, reject traversal-looking text, or verify that the gate file still exists.
- question rule: `question` is read as `str(data.get("question", ""))`; missing values become `""`, JSON `null` becomes `"None"`, and the full normalized text is stored on the gate record.
- gate rule: a non-empty file path creates or replaces exactly one gate record keyed by that path on the connected workflow; existing gates at other file paths are preserved.
- workflow creation rule: if no registry entry exists for the connected container id, the applier creates a placeholder workflow via [upsert workflow](workflow-registry.md#method-upsert-workflow) using the id-derived default name, then applies the blocked state and gate to that new record.
- metadata rule: unlike the residual HTTP [blocked push payload](../blocked-push-payload.md), the websocket applier does not hydrate Docker volume metadata, repository identity, workflow type, run id, or current node; it preserves whatever registry state already exists for those fields.
- notification rule: the blocked notification message is the workflow display name after upsert, followed by `": "`, followed by the normalized question truncated by the [question notification limit](groom-app-module.md#field-question-notify-limit).
- wire rule: everything this layer emits is JSON. The question reaches the browser twice — truncated as the notify frame's `message` string, and whole inside the run's detail payload — and in neither case is it interpolated into markup or into script source. There is no escaping step on this path that can be got wrong.
- ordering: the gate mutation completes before the workflow snapshot is projected, and the state and detail payloads are broadcast before the notify frame, so a tab rendering frames in arrival order raises the alert against a row that already reads blocked.
- output: no return value; completion means registry mutation, gate replacement, state and detail projection, and both broadcasts have completed or an upstream exception has interrupted the operation.
- transport response: the layer does not send a websocket reply frame, RPC result, acknowledgement, or error frame for the blocked event.

## Effects

- Creates or updates the workflow registry entry for `container_id` through [upsert workflow](workflow-registry.md#method-upsert-workflow), creating a placeholder workflow named from the normalized id if the registry entry is somehow absent after hello establishment.
- Writes [workflow state](workflow-state.md) `BLOCKED` to the stored [workflow container](workflow-container.md).
- Creates one [gate info](gate-info.md) record with `workflow_id` equal to `container_id`, `file_path` equal to the normalized frame path, `question` equal to the normalized question string, and default gate status.
- Stores the gate record in the workflow's gate map at the normalized file-path key, replacing any previous record for the same path while preserving other gate keys.
- Reads the current workflow registry snapshot through [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot) after the gate mutation.
- Projects one [dashboard state payload](../dashboard-state-payload.md) through [state message](groom-projection-module.md#method-state-message) and broadcasts it to every registered browser client, so each tab re-renders its runs fleet view and status bar from the new snapshot.
- Projects this run's refreshed detail through [detail message](groom-projection-module.md#method-detail-message) and pushes it to the tabs the [run watch registry](run-watch-registry.md) records as watching this run, so an operator with that run already open sees the new gate without asking for it.
- Broadcasts one separate [dashboard notify message](../dashboard-notify-message.md) — `{"type": "notify", "message": ...}`, the workflow display name and the question truncated by the [question notification limit](groom-app-module.md#field-question-notify-limit) — through [broadcast dashboard message](dashboard-client-queue-set.md#method-broadcast-dashboard-message), targeting the dashboard browser client queues registered at broadcast time. The alert is a separate frame rather than a field on the state payload precisely so it fires on the block itself rather than on every clock tick that re-pushes the same blocked row.
- Does not register or unregister sidecar sockets, resolve pending RPCs, send acknowledgement frames, answer gate files, clear other gate records, persist workflow state outside memory, append answer logs, prune vanished workflows, inspect Docker volumes, read workspace files, compute diffs, hydrate workflow metadata, update current node, or update repository identity. It emits no HTML, no inline script, and no per-producer markup of any kind: the two frames it sends are the same ones the live clock and the HTTP push endpoints send.

## Methods

### method-apply-socket-blocked

- sig: `async _apply_socket_blocked(container_id: str, data: dict) -> None`
- abstract: false
- raises: propagates ordinary exceptions from workflow upsert, gate construction, state or detail projection, or dashboard broadcast; intentionally raises nothing for an empty file path.
- code: groom/groom/app.py::_apply_socket_blocked

Applies one live sidecar blocked delta to the in-memory dashboard state and emits the two browser-facing JSON frames that follow from it. The method is called only after [run sidecar websocket session](../http/groom.md#run-sidecar-websocket-session) has accepted a sidecar `hello`, registered a live connection, and dispatched a `blocked` frame for that connected container.

#### Effects

- Reads: `file_path` and `question` from the supplied [sidecar websocket frame](../sidecar-websocket-frame.md); other frame keys have no effect.
- Normalizes: both values with `str(value)` and uses `""` when the key is absent.
- Guards: returns immediately when the normalized file path is empty.
- Calls: [upsert workflow](workflow-registry.md#method-upsert-workflow) with the connected container id and [workflow state](workflow-state.md) `BLOCKED`.
- Creates: one [gate info](gate-info.md) record with default status for the connected workflow id, normalized file path, and normalized question.
- Writes: stores the gate record in the returned workflow's gate map under the normalized file-path key, replacing only that key.
- Calls: [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot) after the gate write.
- Calls: [broadcast shell](dashboard-shell-broadcaster.md#method-broadcast-shell) with this container id, which projects and broadcasts the state payload and then pushes this run's refreshed detail to its watchers.
- Calls: [broadcast dashboard message](dashboard-client-queue-set.md#method-broadcast-dashboard-message) a second time with the [dashboard notify message](../dashboard-notify-message.md), whose text is the workflow display name and the question truncated by the [question notification limit](groom-app-module.md#field-question-notify-limit).
- Preserves: existing workflow identity, repository fields, current node, run id, workflow type, workspace volume, runs volume, exit code, unrelated gates, log entries, sidecar registrations, and dashboard-client registrations except for the broadcast send itself.
- Emits: no Python return value, no HTTP body, no sidecar websocket message, and no dashboard command acknowledgement.

## Algorithms

### algorithm-apply-one-blocked-delta

- step: Receive the connected container id from the sidecar session and the decoded blocked frame selected by the session dispatcher.
- step: Convert `data.get("file_path", "")` to text and stop with no side effects when that text is empty.
- step: Convert `data.get("question", "")` to text so the gate and notification preview have a deterministic string.
- step: Upsert the workflow container with state `BLOCKED`, preserving existing identity, current node, repository fields, workflow type, volume metadata, run id, exit code, and unrelated fields that this delta does not supply.
- step: Store a gate record under the normalized file path; if that key already exists, replace that one gate, and if other gate keys exist, leave them in place.
- step: Read the current workflow-registry snapshot after mutation so the projected state payload reflects the new blocked state and gate.
- step: Broadcast that state payload to every registered dashboard client queue, then push this run's refreshed detail to the queues watching it.
- step: Broadcast one further notify frame whose `message` is the workflow name and the question prefix capped by the [question notification limit](groom-app-module.md#field-question-notify-limit).

## Failure Semantics

- Workflow-upsert, gate-record construction, projection, or broadcast exceptions are not converted into a blocked-specific result; they propagate to the websocket session handler after any earlier registry mutation has already happened.
- If projection or broadcasting fails after the workflow has been marked blocked and the gate has been stored, the in-memory workflow state remains updated while some or all connected browser clients may not receive the state, detail, or notify frame. A tab that misses the state frame recovers it from the next clock tick or from an [HTTP resync](../http/groom.md#get-dashboard-state); a tab that misses the notify frame never learns of it, because the alert is an edge and is not replayed.
- An empty normalized `file_path` is the only swallowed input condition; it returns without failure and without side effects.
- A `file_path` value that string-normalizes to non-empty text is accepted regardless of whether it names a real gate context file; any stale, unsafe-looking, or non-workspace path text becomes only the in-memory gate key and rendered gate path until a later answer or discovery path handles it.
