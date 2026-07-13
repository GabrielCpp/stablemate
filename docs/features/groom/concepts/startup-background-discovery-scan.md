---
type: concept
slug: startup-background-discovery-scan
title: Startup background discovery scan
---
# Startup background discovery scan

Startup background discovery scan is the coroutine scheduled by the [schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan) startup invocation after the groom server application enters its startup lifecycle. It runs the [reconcile workflow fleet](workflow-registry.md#method-reconcile-workflow-fleet) method once, then always clears the [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) and asks the [dashboard shell broadcaster](dashboard-shell-broadcaster.md) to publish the current dashboard shell so connected browser tabs stop showing provisional discovery state. The [Groom app module](groom-app-module.md#method-background-scan) folds this private coroutine into the server-startup path, while the [serve dashboard and startup discovery](../flows/serve-dashboard-and-startup-discovery.md) flow describes the operator-visible dashboard transition that results from it.

- code: groom/groom/app.py::_background_scan
- verify: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes
- verify: groom/tests/test_app.py::test_background_scan_clears_scanning_on_error
- refs: [schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan), [reconcile workflow fleet](workflow-registry.md#method-reconcile-workflow-fleet), [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md), [dashboard shell broadcaster](dashboard-shell-broadcaster.md)

## Contract

- sig: `async _background_scan() -> None`
- purpose: complete the initial Docker-backed workflow discovery pass after server startup has scheduled it, without blocking the startup hook that created the task.
- input: no arguments; all state is read from the process-local groom modules and the local Docker environment reached by reconciliation.
- output: no return value; successful completion means reconciliation finished, the discovery-loading flag is false, and the completion dashboard shell broadcast helper completed.
- scheduling: intended to run as exactly one process-local asyncio task created by the startup hook for each groom application startup; the coroutine itself does not create or retain its task handle.
- state cleanup: clears the dashboard discovery scanning flag in a `finally` path, so the flag is cleared after both successful reconciliation and reconciliation exceptions.
- broadcast ordering: broadcasts the dashboard shell only after setting the scanning flag to false, so rendered inbox empty state reflects completion rather than in-progress discovery.
- task ownership: the scheduled task handle is held outside this coroutine by [field-scan-task](groom-app-module.md#field-scan-task); this coroutine does not reschedule itself, retry itself, or expose a cancellation or completion handle.
- errors: reconciliation exceptions are not intentionally swallowed; the cleanup flag clear still happens, then the completion broadcast is awaited. Broadcast exceptions are not converted to a domain-specific result and can be the observed task exception if the broadcast fails while cleanup is running.

## Methods

### method-background-scan

- sig: `async _background_scan() -> None`
- abstract: false
- raises: propagates reconciliation failures when cleanup broadcast succeeds; propagates completion-broadcast failures when rendering or client-queue broadcast fails during cleanup.
- code: groom/groom/app.py::_background_scan
- verify: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes
- verify: groom/tests/test_app.py::test_background_scan_clears_scanning_on_error

Runs the server-startup discovery work in the already-created background task. The method has no caller-supplied arguments and no return payload; its externally visible contract is the sequence of registry reconciliation, discovery-loading flag cleanup, and dashboard shell broadcast.

#### Effects

- Calls: [reconcile workflow fleet](workflow-registry.md#method-reconcile-workflow-fleet) exactly once before any local cleanup action.
- Writes: sets [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) to `False` in the cleanup path after the reconciliation await exits normally, raises, or is interrupted by task cancellation.
- Calls: [dashboard shell broadcaster](dashboard-shell-broadcaster.md) once after writing the scanning flag to `False`.
- Emits: no direct return value, HTTP response, websocket frame, sidecar frame, browser event, log entry, or persisted artifact; websocket text is emitted only by the downstream broadcaster.

#### Failure Behavior

- Reconciliation success plus broadcast success: the method returns `None` after the shell broadcast completes.
- Reconciliation failure plus broadcast success: the reconciliation exception remains the task failure after the flag has been cleared and the shell broadcast has completed.
- Reconciliation success plus broadcast failure: the broadcast exception becomes the task failure after the flag has been cleared.
- Reconciliation failure plus broadcast failure: the cleanup broadcast exception can replace the reconciliation exception as the task's observed failure; the scanning flag has still already been cleared.
- Task cancellation during reconciliation: the cleanup path still attempts to clear the flag and run the completion broadcast before the cancellation outcome is observed by the task.

## Effects

- Calls: [reconcile workflow fleet](workflow-registry.md#method-reconcile-workflow-fleet) once to install discovered workflow containers and prune vanished registry entries when Docker presence can be read.
- Writes: sets the [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) value to `False` after the reconciliation attempt exits, regardless of whether reconciliation returned or raised.
- Calls: [dashboard shell broadcaster](dashboard-shell-broadcaster.md) after clearing the scanning flag, causing connected browser dashboard clients to receive an out-of-band shell fragment for the current workflow registry and loading state.
- Emits: no HTTP response, sidecar websocket frame, browser command frame, persisted file, log entry, or return payload directly; any dashboard websocket output is produced by the broadcaster helper.
- Preserves: the scheduled task handle, sidecar websocket registrations, gate answer locks except through reconciliation pruning, answer logs, static dashboard assets, and operator gate files.
- Does not: set the scanning flag to true, schedule itself, serialize overlapping refresh scans, answer gate files, start or stop containers, render worker detail, read file contents, compute diffs, or retry failed discovery.

## Algorithms

### algorithm-startup-background-scan

- step: Enter the startup discovery coroutine after [schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan) has already created and stored the task.
- step: Await [reconcile workflow fleet](workflow-registry.md#method-reconcile-workflow-fleet) once, allowing it to install discovered workflow containers and prune vanished registry entries when Docker presence can be read.
- step: Enter cleanup regardless of reconciliation success, reconciliation failure, or task cancellation during reconciliation.
- step: Set the [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) to `False` before rendering or broadcasting any completion shell fragment.
- step: Await [dashboard shell broadcaster](dashboard-shell-broadcaster.md) so registered dashboard websocket clients are offered an out-of-band shell fragment whose inbox rendering no longer treats startup discovery as in flight.
- step: Return `None` when reconciliation and broadcast both complete; otherwise let the observed reconciliation, cancellation, or broadcast exception fail the background task.

## Failure Behavior

- Reconciliation failure: when completion broadcast succeeds, the reconciliation exception propagates out of the coroutine after the `finally` cleanup path runs; the scanning flag is still false before the exception leaves.
- Completion broadcast failure: the exception propagates out of the coroutine after the scanning flag has already been cleared, including the case where the broadcast fails while the coroutine is already unwinding a reconciliation exception.
- No connected dashboard clients: the broadcaster still receives the rendered shell fragment and has no clients to enqueue it for; the background scan has no separate fallback channel.
