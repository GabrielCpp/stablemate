---
type: flow
slug: operator-refreshes-workflow-fleet
title: Operator refreshes workflow fleet
---
# Operator refreshes workflow fleet

This journey covers the as-built manual refresh path from either dashboard
rescan control to [POST /refresh](../http/groom.md#post-refresh), the
[dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md)
pre-scan broadcast, one Docker-backed [workflow discovery scan](../concepts/workflow-discovery-scan.md),
registry replacement and prune through the [workflow registry](../concepts/workflow-registry.md),
and the two [dashboard state payload](../dashboard-state-payload.md) frames that
re-render the runs list and status bar in every connected
[groom dashboard](../gui/screens/groom-dashboard.md) tab. The path is available
from the settings pane through [rescan containers from settings](../gui/screens/groom-dashboard.md#rescan-containers-from-settings)
and from the always-visible status bar through [rescan containers from statusbar](../gui/screens/groom-dashboard.md#rescan-containers-from-statusbar);
both controls share the same browser refresh helper and server invocation.

The refresh response body is not what the operator sees. `POST /refresh` returns
a count for scripted callers; every visible consequence arrives on the socket as
the same `state` frame the 5-second clock pushes, applied through the same one
apply path. That is why the browser never reads the response — there is nothing
in it the socket does not already deliver, in a shape the renderer already knows.

- start: the groom server is running, a browser has loaded the [groom dashboard](../gui/screens/groom-dashboard.md),
  and the tab normally has an active [WS /ws](../http/groom.md#websocket-dashboard)
  dashboard websocket so state broadcasts can reach it. The process-local
  [workflow registry](../concepts/workflow-registry.md) may be empty, stale,
  partially hydrated by sidecar pushes, or already reconciled by startup
  discovery; the manual refresh does not require a selected run, selected
  repository, open settings pane, or idle startup scan.
- code: groom/groom/assets/dashboard.js::doRefresh
- code: groom/groom/assets/dashboard.js::Fleet
- code: groom/groom/assets/dashboard.js::StatusBar
- code: groom/groom/app.py::refresh
- code: groom/groom/app.py::_broadcast_shell
- code: groom/groom/app.py::_reconcile
- code: groom/groom/discovery.py::scan
- code: groom/groom/discovery.py::present_container_ids
- code: groom/groom/state.py::prune_workflows
- code: groom/groom/projection.py::state_message
- steps:
  1. The operator chooses a refresh entry point. In settings mode, activating
     [rescan containers from settings](../gui/screens/groom-dashboard.md#rescan-containers-from-settings)
     starts the shared refresh helper from the `Rescan containers` button. From
     any dashboard mode, activating [rescan containers from statusbar](../gui/screens/groom-dashboard.md#rescan-containers-from-statusbar)
     starts the same helper from the status-bar icon button named `Rescan
     containers (reconcile + prune)`.
  2. The refresh helper treats busy state as local to the activated button. If
     that same button already has `data-busy`, the activation is ignored before
     any network request. Otherwise the helper sets `data-busy="1"`, adds
     `spinning`, and sends exactly one `POST /refresh` with no query string,
     required headers, or request body. It does not read the response body,
     synchronize busy state with the other refresh button, cancel other
     refreshes, navigate, move focus, or send a websocket frame.
  3. [Refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) sets the
     [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md)
     to `True` *before* Docker reconciliation starts, then broadcasts one
     [dashboard state payload](../dashboard-state-payload.md) built from the
     current registry snapshot through the [dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md).
     The flag rides in that JSON frame as a `scanning` boolean; the server picks
     no wording for it.
  4. Every registered dashboard websocket client queue receives that pre-scan
     frame and applies it through the store. The runs list and status bar
     re-render from the new snapshot; when the fleet is empty *and* the operator
     is not mid-filter, the `scanning` flag is what makes the list read
     `Discovering containers…` instead of `No workhorse runs — nothing is
     running.` — a fleet that has not been scanned yet must read as loading, not
     as finished and empty, but an empty filter result is the honest answer and
     is left alone. Open run detail, repository menus, files, diffs, the command
     palette, selected-run and selected-repository state, the toast stack, and
     the browser URL are not part of this frame and do not change.
  5. The endpoint runs [reconcile workflow fleet](../concepts/workflow-registry.md#method-reconcile-workflow-fleet)
     on the default thread pool. Reconciliation calls the
     [workflow discovery scan](../concepts/workflow-discovery-scan.md), which
     reads Docker's all-container listing, resolves each candidate workhorse
     container by requiring the `/workflow`, `/runs`, and `/workspace` mount
     contract, prefers a running-container sidecar snapshot when one is
     available, and otherwise reconstructs state from the workflow run and
     workspace volumes.
  6. For every discovered [workflow container](../concepts/workflow-container.md),
     reconciliation replaces the process-local registry entry keyed by that
     container id with the discovered snapshot. Replacement is authoritative for
     that refresh result: the discovered workflow record supplies the visible
     identity, workflow type, state, current node, volume names, exit code, and
     open gate map for that container until a later push, sidecar delta, answer,
     or refresh mutates it again.
  7. After installing discovered records, reconciliation asks discovery for
     [present container ids](../concepts/workflow-discovery-scan.md#method-present-container-ids).
     When Docker returns a set, [prune workflows](../concepts/workflow-registry.md#method-prune-workflows)
     removes registry entries whose ids are absent from that set and forgets
     their per-gate answer locks. When Docker returns `None` to represent an
     unavailable present-id lookup, pruning is skipped so a transient Docker
     outage cannot erase workflows that were already visible.
  8. Whether reconciliation succeeds or raises, the endpoint clears the scanning
     flag in its reconciliation cleanup path. On the successful path only, it
     broadcasts a second [dashboard state payload](../dashboard-state-payload.md)
     after the flag is false, then returns JSON `{ "ok": true, "count": n }`,
     where `count` is the number of workflows returned by the discovery scan
     before stale-entry pruning is considered.
  9. Connected dashboard tabs apply the post-scan frame through the same store
     write and the same render path. Newly discovered runs appear as rows keyed
     by run id, vanished containers disappear when pruning was safe, stale rows
     remain when Docker presence could not be trusted, and status-bar counts
     reflect the current registry snapshot. Rows the operator can already see
     keep their DOM nodes, so a rescan does not disturb scroll position or move
     focus off a row.
  10. When the browser fetch promise settles, the refresh helper removes
      `data-busy` and `spinning` from the button it was given. The status-bar
      button is rendered by the status-bar island, but reconciliation reuses that
      element across re-renders and its declared `class` prop does not change
      between them, so the imperatively added `spinning` class survives every
      frame that arrives mid-request and the same element reference is still the
      live button when cleanup runs.
- end: every connected dashboard tab that still has an active dashboard
  websocket has received the refresh state frames that the server successfully
  broadcast. The process-local workflow registry contains the discovered
  workhorse containers plus any previously visible entries retained because
  Docker presence was unavailable, minus safely pruned vanished containers; the
  scanning flag is false on successful reconciliation completion; and the HTTP
  caller receives only the success JSON count rather than row-level details.
  Failed pre-scan broadcast leaves the scanning flag true because reconciliation
  never starts, reconciliation failure clears the scanning flag but skips the
  post-scan broadcast and success response, and post-scan broadcast failure
  propagates after the registry has already been reconciled and the scanning
  flag cleared.
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers,
  groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable,
  groom/tests/test_state.py::test_prune_drops_absent_keeps_present,
  groom/tests/test_state.py::test_prune_empty_present_removes_everything,
  groom/tests/test_state.py::test_prune_also_forgets_gate_locks_of_removed,
  groom/tests/test_projection.py::test_state_message_reports_whether_discovery_is_still_running,
  groom/tests/test_projection.py::test_status_bar_counts_states,
  groom/tests/test_projection.py::test_state_message_is_json_serializable
- screenshot: docs/features/groom/gui/screenshots/operator-refreshes-workflow-fleet-settings-idle.png
- screenshot: docs/features/groom/gui/screenshots/operator-refreshes-workflow-fleet-post-scan.png
