---
type: concept
slug: startup-background-discovery-scan
title: Startup background discovery scan
---
# Startup background discovery scan

Startup background discovery scan is the private coroutine that [schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan) places in the groom application's startup task slot. It reconciles the [workflow registry](workflow-registry.md) once through [reconcile workflow fleet](workflow-registry.md#method-reconcile-workflow-fleet), then clears the [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) and asks the [dashboard shell broadcaster](dashboard-shell-broadcaster.md) to send the settled state to connected dashboard tabs. [Groom app module](groom-app-module.md#method-background-scan) records the module-level task owner, and [serve dashboard and startup discovery](../flows/serve-dashboard-and-startup-discovery.md) describes the resulting operator-visible transition.

The coroutine has no input or task-management API: its startup hook owns scheduling and its caller observes completion or failure through that task. It neither retries discovery nor serializes it with manual refreshes.

- code: groom/groom/app.py::_background_scan
- tests: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes
- tests: groom/tests/test_app.py::test_background_scan_clears_scanning_on_error

## Methods

### method-background-scan

- sig: `async _background_scan() -> None`
- abstract: false
- does: awaits one workflow-registry reconciliation before its cleanup path.
- verify: count(subject="workflow reconciliations performed by one startup scan", equals=1)
- does: clears the discovery scanning flag in cleanup after reconciliation returns, raises, or is cancelled.
- verify: json_path(path="scanning", equals=False)
- does: awaits one dashboard-shell broadcast after clearing the discovery scanning flag.
- verify: emitted(event="dashboard state payload", count=1)
- raises: propagates a reconciliation failure after cleanup when the completion broadcast succeeds.
- raises: propagates a completion-broadcast failure after the discovery scanning flag has been cleared.
- returns: `None` after reconciliation and the completion broadcast both succeed.
- code: groom/groom/app.py::_background_scan
- tests: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes
- tests: groom/tests/test_app.py::test_background_scan_clears_scanning_on_error

The `finally` block deliberately runs after a successful scan, a reconciliation error, or task cancellation. It does not shield either await: if reconciliation and the cleanup broadcast both fail, the broadcast failure is the task's observed exception. The downstream broadcaster may enqueue zero messages when no tabs are connected; the coroutine still invokes it and has no alternate delivery path.
