---
type: flow
slug: serve-dashboard-and-startup-discovery
title: Serve dashboard and startup discovery
---
# Serve dashboard and startup discovery

This journey covers the as-built path from the operator running
[`groom serve`](../groom-cli.md#serve) to the browser seeing the
[groom dashboard](../gui/screens/groom-dashboard.md) shell, mounting its islands,
opening [WS /ws](../http/groom.md#websocket-dashboard), receiving the initial
[dashboard state payload](../dashboard-state-payload.md), and then receiving the
post-startup-discovery broadcast that replaces the
[runs fleet view](../runs-fleet-view.md) rows and the status bar. The startup
portion is scheduled by the [groom server](../http/groom.md) app factory — three
independent hooks, not one — and the discovery pass itself is completed by the
[startup background discovery scan](../concepts/startup-background-discovery-scan.md);
the loading state is carried by the
[dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md),
and every live state update is emitted through the
[dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md).

The HTML the server returns is static and identical for every request. It contains
no rows, no counts and no data of any kind — only the empty ids the islands mount
into. Everything the operator reads arrives afterwards as JSON, over the socket or
over [GET /api/state](../http/groom.md#get-dashboard-state), and both routes end in
the same [apply-state](../concepts/dashboard-client-store.md#method-apply-state)
call. That is the whole point of serving a fixed document: the startup path and the
resync path are not two renderers that can drift apart, and the first frame a fresh
tab receives is byte-identical to the body a recovering tab polls.

- start: an operator invokes `groom serve` on a trusted host with a parseable
  host and port. The groom process has not yet accepted dashboard requests for
  this run; its process-local [workflow registry](../concepts/workflow-registry.md)
  starts empty, and the [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md)
  starts `True` so an initially empty fleet renders as discovery in progress
  rather than as a finished, empty answer.
- code: groom/groom/cli.py::serve
- code: groom/groom/app.py::create_app
- code: groom/groom/app.py::_spawn_scan
- code: groom/groom/app.py::_background_scan
- code: groom/groom/app.py::_spawn_rules
- code: groom/groom/app.py::_spawn_live
- code: groom/groom/app.py::_live_loop
- code: groom/groom/app.py::index
- code: groom/groom/app.py::dashboard_ws
- code: groom/groom/app.py::_broadcast_shell
- code: groom/groom/projection.py::state_message
- code: groom/groom/assets/dashboard.js::startConnection
- code: groom/groom/assets/dashboard.js::connect
- code: groom/groom/assets/dashboard.js::applyState
- steps:
  1. [`groom serve`](../groom-cli.md#serve) validates the parsed command shape,
     optionally warns when the selected bind host is non-loopback and the
     warning-suppression flag is absent, constructs the
     [groom server](../http/groom.md) application, and hands it to the server
     runner on the selected host and port. The command itself does not inspect
     Docker, project dashboard rows, authenticate clients, or wait for discovery.
  2. The application factory registers **three** startup hooks, not one, because
     they answer to three different clocks and none of them may block the others.
     [Schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan)
     creates the one-shot Docker reconciliation task;
     [schedule alert rule ticker](../http/groom.md#schedule-alert-rule-ticker)
     prunes the durable store once and then starts the absence-driven STALL/BUDGET
     evaluation loop; and [schedule live clock](../http/groom.md#schedule-live-clock)
     starts the periodic state push. Two shutdown hooks cancel the two long-lived
     loops; the discovery task is one-shot and is not cancelled.
  3. Each startup hook only *schedules* its task and returns, so lifespan startup
     finishes and the port binds immediately rather than after a full Docker scan.
     The scan task, the rules task, and the live task are stored in separate
     process-local slots; a failure in any one of them cannot prevent the server
     from accepting connections.
  4. The scheduled [startup background discovery scan](../concepts/startup-background-discovery-scan.md)
     runs one [reconcile workflow fleet](../concepts/workflow-registry.md#method-reconcile-workflow-fleet)
     pass in the background. Reconciliation installs discovered workflow
     containers into the registry and prunes vanished registry entries only when
     Docker can report the present container-id set; transient Docker presence
     failure leaves existing registry entries visible.
  5. A browser requests [GET /](../http/groom.md#get-root-dashboard-html). The
     [serve root dashboard html](../http/groom.md#serve-root-dashboard-html)
     invocation returns the packaged dashboard document exactly as loaded from
     `groom/groom/templates/dashboard.html` — the activity rail, the five empty
     pane roots, the empty `#statusbar`, the repository combobox, the command
     palette dialog, the toast region, the vendored asset links, and one
     `<script type="module">` tag. It contains no workflow rows, counts, fleet
     data, sidecar state, answer forms, or discovery results, and it is the same
     bytes for every request and every operator.
  6. The module script mounts each island into the id the static shell already
     ships, against the empty initial store. That first render is what produces
     the visible skeleton: an empty runs list, a status bar with zero counts, and
     a [connection chip](../gui/screens/groom-dashboard.md#connection-chip)
     reporting its starting phase. No island waits for data to exist before
     mounting, so there is no arrangement of network failures in which the page
     stays blank.
  7. The client starts its connection supervisor, which opens
     [WS /ws](../http/groom.md#websocket-dashboard) and simultaneously begins the
     one-second evaluation tick of the
     [dashboard connection state machine](../concepts/dashboard-connection-state-machine.md).
     The socket is opened for data, not for truth about the connection: the phase
     the chip shows is derived from how recently a *message* arrived, so a socket
     that opened and then silently died is not reported as live.
  8. [Run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session)
     accepts the connection, creates one browser-client queue, registers it
     *before* emitting anything, and immediately sends one
     [dashboard state payload](../dashboard-state-payload.md) built from the
     current [workflow registry](../concepts/workflow-registry.md) snapshot. The
     registration-then-send order is what makes a broadcast racing the handshake
     land as a second frame rather than be dropped.
  9. The tab applies that first frame through
     [apply state](../concepts/dashboard-client-store.md#method-apply-state) — the
     same one write the resync path uses. The
     [runs live region](../gui/screens/groom-dashboard.md#runs-live-region)
     renders either [run rows](../gui/screens/groom-dashboard.md#run-row) or, when
     the fleet is empty *and* no filter is typed *and* the frame's `scanning` flag
     is set, `Discovering containers…`. An empty fleet with the flag clear reads
     `No workhorse runs — nothing is running.` instead: not-yet-scanned and
     scanned-and-empty are different facts and the frame carries which one it is.
     The status bar renders the same snapshot's blocked/running/idle/finished
     counts.
  10. When startup reconciliation exits, the background scan clears the
      [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md)
      to `False` in its cleanup path, even if reconciliation raised before
      completion. It then calls the [dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md)
      so every currently registered dashboard client receives one current state
      payload after the loading state has ended — reaching every open tab through
      exactly the path `/refresh` uses.
  11. Each tab applies the post-discovery frame through the same store write and
      the same render path as the first one. Discovered runs appear as rows keyed
      by run id, so rows that were already visible keep their DOM nodes and
      neither scroll position nor focus moves; an empty discovered fleet now reads
      as `No workhorse runs — nothing is running.` rather than as loading. Selected
      run detail, repository menus, files, diffs, telemetry, and toasts are not
      part of this frame and change only through their own later interactions.
  12. From then on the [live clock](../http/groom.md#schedule-live-clock) pushes a
      fresh state payload — plus one detail payload per *watched* run — every tick,
      skipping the work entirely when no client is connected. This is what keeps
      the clock-derived half of each row (liveness, `silent 4m`, `in node 12m`)
      from freezing at whatever the last state change made it, since a run going
      quiet is an absence and an absence cannot be pushed. The same tick doubles as
      the socket's heartbeat: it fires whether or not anything changed, which is
      what lets the browser read silence as a dead connection rather than as a
      quiet fleet, and hand the tab to the
      [resync poller](../concepts/dashboard-resync-poller.md) when it does.
- end: the server is running with the dashboard route table available and all
  three startup hooks scheduled; at least one browser tab can hold a live `/ws`
  session and is showing a connection phase derived from message recency; the
  startup discovery task has either completed reconciliation or failed after
  clearing the scanning flag; and the visible runs list and status bar are
  projected from the current process-local workflow registry through the state
  payload. The process remains unauthenticated and single-process, with no durable
  persistence of the workflow registry, the connected clients, their run
  subscriptions, or the scanning flag beyond process memory.
- verify: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes,
  groom/tests/test_app.py::test_background_scan_clears_scanning_on_error,
  groom/tests/test_app.py::test_the_clock_refreshes_every_open_pane_alongside_the_fleet,
  groom/tests/test_projection.py::test_state_message_reports_whether_discovery_is_still_running,
  groom/tests/test_projection.py::test_status_bar_counts_states,
  groom/tests/test_projection.py::test_state_message_is_json_serializable,
  groom/tests/test_connection_state.py::test_open_socket_receiving_frames_is_live,
  groom/tests/test_connection_state.py::test_open_but_silent_socket_goes_stale_and_starts_resyncing,
  groom/tests/test_dashboard_client.py::test_the_client_module_parses,
  groom/tests/test_dashboard_client.py::test_htmx_is_gone_from_the_shipped_surface
- screenshot: docs/features/groom/gui/screenshots/serve-dashboard-and-startup-discovery-post-discovery.png
