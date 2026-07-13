---
type: flow
slug: operator-refreshes-workflow-fleet
title: Operator refreshes workflow fleet
---
# Operator refreshes workflow fleet

This journey covers the as-built manual refresh path from either dashboard
rescan control to [POST /refresh](../http/groom.md#post-refresh), the
[dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md)
pre-scan shell update, one Docker-backed [workflow discovery scan](../concepts/workflow-discovery-scan.md),
registry replacement and prune through the [workflow registry](../concepts/workflow-registry.md),
and the websocket out-of-band [dashboard shell fragment](../dashboard-shell-fragment.md)
updates that replace the operator inbox and status bar in every connected
[groom dashboard](../gui/screens/groom-dashboard.md) tab. The path is available
from the settings pane through [rescan containers from settings](../gui/screens/groom-dashboard.md#rescan-containers-from-settings)
and from the always-visible status bar through [rescan containers from statusbar](../gui/screens/groom-dashboard.md#rescan-containers-from-statusbar);
both controls share the same browser refresh layer and server invocation.

- start: the groom server is running, a browser has loaded the [groom dashboard](../gui/screens/groom-dashboard.md),
  and the tab normally has an active [WS /ws](../http/groom.md#websocket-dashboard)
  dashboard websocket so shell broadcasts can reach it. The process-local
  [workflow registry](../concepts/workflow-registry.md) may be empty, stale,
  partially hydrated by sidecar pushes, or already reconciled by startup
  discovery; the manual refresh does not require a selected worker, selected
  repository, open settings pane, or idle startup scan.
- code: groom/groom/templates/dashboard.html::doRefresh
- code: groom/groom/app.py::refresh
- code: groom/groom/app.py::_broadcast_shell
- code: groom/groom/app.py::_reconcile
- code: groom/groom/discovery.py::scan
- code: groom/groom/discovery.py::present_container_ids
- code: groom/groom/state.py::prune_workflows
- code: groom/groom/render.py::render_shell_data
- steps:
  1. The operator chooses a refresh entry point. In settings mode, activating
     [rescan containers from settings](../gui/screens/groom-dashboard.md#rescan-containers-from-settings)
     starts the shared refresh layer from the `Rescan containers` button. From
     any dashboard mode, activating [rescan containers from statusbar](../gui/screens/groom-dashboard.md#rescan-containers-from-statusbar)
     starts the same layer from the status-bar icon button named `Rescan
     containers (reconcile + prune)`.
  2. The browser refresh layer treats busy state as local to the activated
     button. If that same button already has `data-busy`, the activation is
     ignored before any network request. Otherwise the layer sets
     `data-busy="1"`, adds `spinning`, and sends exactly one `POST /refresh`
     request with no query string, required headers, or request body. It does
     not inspect the eventual JSON response, synchronize busy state with the
     other refresh button, cancel other refreshes, navigate, move focus, or send
     a websocket frame.
  3. [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) sets the
     [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md)
     to `True` before Docker reconciliation starts. It then calls the
     [dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md)
     through the server shell-render path, producing one [dashboard shell fragment](../dashboard-shell-fragment.md)
     with out-of-band swap markers from the current registry snapshot.
  4. Every registered dashboard websocket client queue receives that pre-scan
     shell fragment. The browser websocket extension applies it as out-of-band
     swaps for `#inbox-list` and `#statusbar`; when the inbox would otherwise be
     empty and unfiltered, the scanning flag makes the inbox render
     `Discovering containers...` instead of the normal empty-inbox message.
     Selected worker detail, repository menus, files, diffs, command palette,
     selected worker state, selected repository state, toast stack, and browser
     URL are outside the shell fragment and remain unchanged.
  5. The endpoint runs [reconcile workflow fleet](../concepts/workflow-registry.md#method-reconcile-workflow-fleet).
     Reconciliation calls the [workflow discovery scan](../concepts/workflow-discovery-scan.md),
     which reads Docker's all-container listing, resolves each candidate
     workhorse container by requiring the `/workflow`, `/runs`, and `/workspace`
     mount contract, prefers a running-container sidecar snapshot when one is
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
     broadcasts a second [dashboard shell fragment](../dashboard-shell-fragment.md)
     after the flag is false, then returns JSON `{ "ok": true, "count": n }`,
     where `count` is the number of workflows returned by the discovery scan
     before stale-entry pruning is considered.
  9. Connected dashboard tabs apply the post-scan shell broadcast to the same
     `#inbox-list` and `#statusbar` targets. Newly discovered blocked workflows
     appear as inbox rows, vanished containers disappear when pruning was safe,
     stale rows remain when Docker presence could not be trusted, and status-bar
     counts reflect the current registry snapshot. The refresh response body is
     not displayed by the browser; visible convergence comes from the websocket
     shell update.
  10. When the browser fetch promise settles, the refresh layer removes
      `data-busy` and `spinning` from the original activated button object. If
      the activated status-bar button was replaced by an out-of-band status-bar
      swap during the request, the visible replacement is already an idle button;
      the cleanup still targets the old element reference and produces no extra
      UI state.
- end: every connected dashboard tab that still has an active dashboard
  websocket has received the refresh shell updates that the server successfully
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
  groom/tests/test_render.py::test_empty_inbox_shows_spinner_while_scanning,
  groom/tests/test_render.py::test_statusbar_counts_states
