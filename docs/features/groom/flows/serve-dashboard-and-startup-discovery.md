---
type: flow
slug: serve-dashboard-and-startup-discovery
title: Serve dashboard and startup discovery
---
# Serve dashboard and startup discovery

This journey covers the as-built path from the operator running
[`groom serve`](../groom-cli.md#serve) to the browser seeing the
[groom dashboard](../gui/screens/groom-dashboard.md) shell, opening
[WS /ws](../http/groom.md#websocket-dashboard), receiving the initial
[dashboard shell fragment](../dashboard-shell-fragment.md), and then receiving
the post-startup-discovery shell broadcast that replaces the rendered
[operator inbox](../operator-inbox.md) and status bar. The startup portion is
scheduled by the [groom server](../http/groom.md) app factory and completed by
the [startup background discovery scan](../concepts/startup-background-discovery-scan.md);
the UI loading state is controlled by the
[dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md),
and every live shell update is emitted through the
[dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md).

- start: an operator invokes `groom serve` on a trusted host with a parseable
  host and port. The groom process has not yet accepted dashboard requests for
  this run; its process-local [workflow registry](../concepts/workflow-registry.md)
  starts empty, and the [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md)
  starts `True` so an initially empty inbox renders as discovery in progress.
- code: groom/groom/cli.py::serve
- code: groom/groom/app.py::create_app
- code: groom/groom/app.py::_spawn_scan
- code: groom/groom/app.py::_background_scan
- code: groom/groom/app.py::index
- code: groom/groom/app.py::dashboard_ws
- code: groom/groom/render.py::render_shell_data
- steps:
  1. [`groom serve`](../groom-cli.md#serve) validates the parsed command shape,
     optionally warns when the selected bind host is non-loopback and the
     warning-suppression flag is absent, constructs the
     [groom server](../http/groom.md) application, and hands it to the server
     runner on the selected host and port. The command itself does not inspect
     Docker, render dashboard rows, authenticate clients, or wait for discovery.
  2. [schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan)
     runs as the server application's startup hook. It creates exactly one
     process-local task for `_background_scan`, stores that task in the app
     module's scan-task slot, and returns immediately so startup can finish
     without waiting for Docker discovery.
  3. The scheduled [startup background discovery scan](../concepts/startup-background-discovery-scan.md)
     runs one [reconcile workflow fleet](../concepts/workflow-registry.md#method-reconcile-workflow-fleet)
     pass in the background. Reconciliation installs discovered workflow
     containers into the registry and prunes vanished registry entries only when
     Docker can report the present container-id set; transient Docker presence
     failure leaves existing registry entries visible.
  4. A browser requests [GET /](../http/groom.md#get-root-dashboard-html). The
     [serve root dashboard html](../http/groom.md#serve-root-dashboard-html)
     invocation returns the packaged dashboard HTML document exactly as loaded
     from `groom/groom/templates/dashboard.html`, including empty `#inbox-list`
     and `#statusbar` roots, the htmx websocket connection declaration for
     `/ws`, vendored asset links, and the client-side handlers for mode changes,
     row selection, refresh, repository menus, file/diff loading, and toasts.
     This HTTP response contains no workflow rows, counts, dynamic inbox data,
     sidecar state, answer forms, or discovery results.
  5. After the dashboard document loads, htmx opens
     [WS /ws](../http/groom.md#websocket-dashboard). The websocket handler accepts
     the connection, creates one browser-client queue, registers it before
     emitting data, and immediately sends a [dashboard shell fragment](../dashboard-shell-fragment.md)
     rendered from the current [workflow registry](../concepts/workflow-registry.md)
     snapshot with out-of-band swap markers enabled.
  6. The browser applies that initial websocket text frame as htmx out-of-band
     swaps. The [operator inbox](../operator-inbox.md) replacement renders either
     gated worker rows or, if no gated worker matches and discovery is still
     scanning, the `Discovering containers...` loading placeholder. The status
     bar replacement renders the same snapshot's blocked/running/idle/finished
     counts, repository total, worker total, `live` label, statusbar refresh
     button, and command-palette hint.
  7. When startup reconciliation exits, the background scan clears the
     [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md)
     to `False` in its cleanup path, even if reconciliation raised before
     completion. It then calls the [dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md)
     so every currently registered dashboard websocket client receives one
     current out-of-band shell fragment after the loading state has ended.
  8. The browser applies the post-discovery websocket frame to the same
     `#inbox-list` and `#statusbar` targets. Discovered gated workers appear as
     inbox rows; an empty discovered fleet now reads as `No incoming messages --
     inbox zero.` rather than loading; and the status bar reflects the current
     registry counts. Selected worker detail, repository menus, files, diffs,
     notification scripts, and answer-success scripts are not part of this
     startup shell broadcast and are loaded or appended only by their own later
     interactions.
- end: the server is running with the dashboard route table available; at least
  one browser tab can hold a live `/ws` session; the startup discovery task has
  either completed reconciliation or failed after clearing the scanning flag;
  and the dashboard's rendered inbox/statusbar are sourced from the current
  process-local workflow registry through the documented dashboard shell
  fragment. The process remains unauthenticated and single-process, with no
  durable persistence of workflow registry, websocket clients, or the scanning
  flag beyond process memory.
- verify: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes,
  groom/tests/test_app.py::test_background_scan_clears_scanning_on_error,
  groom/tests/test_render.py::test_dynamic_regions_have_stable_ids_and_oob_flag,
  groom/tests/test_render.py::test_empty_inbox_shows_spinner_while_scanning,
  groom/tests/test_render.py::test_statusbar_counts_states
- screenshot: .agents/okf-build/walkthrough/groom/serve-dashboard-and-startup-discovery-post-discovery.png
