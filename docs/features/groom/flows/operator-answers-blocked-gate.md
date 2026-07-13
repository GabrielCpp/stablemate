---
type: flow
slug: operator-answers-blocked-gate
title: Operator answers blocked gate
---
# Operator answers blocked gate

This journey covers the as-built operator path from a workflow becoming blocked,
through the [groom dashboard](../gui/screens/groom-dashboard.md) inbox and worker
detail, to submitting the [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md)
over [WS /ws](../http/groom.md#websocket-dashboard), writing the answered
[operator gate context file](../operator-gate-context-file.md), refreshing live
dashboard state, dispatching the [groom answered script fragment](../groom-answered-script-fragment.md),
and refetching [get worker detail](../http/groom.md#get-worker-detail) for the
selected worker. The entry gate can arrive from [receive blocked push](../http/groom.md#receive-blocked-push),
[workflow discovery scan](../concepts/workflow-discovery-scan.md), or the
[sidecar blocked applier](../concepts/sidecar-blocked-applier.md); once visible,
the answer path is the same selected-worker detail and websocket command flow.

- start: a workflow container has an operator gate whose context file still
  reads `STATUS: AWAITING_OPERATOR`. The groom process is running, at least one
  dashboard tab has loaded the dashboard and opened [WS /ws](../http/groom.md#websocket-dashboard),
  and the workflow is either about to be marked blocked by a push, discovered
  from existing Docker/run state, or already present with an open [gate info](../concepts/gate-info.md)
  record.
- code: groom/groom/app.py::push_blocked
- code: groom/groom/discovery.py::scan
- code: groom/groom/app.py::dashboard_ws
- code: groom/groom/app.py::_handle_command
- code: groom/groom/gates.py::answer_gate
- code: groom/groom/render.py::render_worker_detail
- code: groom/groom/render.py::render_notify_script
- code: groom/groom/render.py::render_answered_script
- code: groom/groom/templates/dashboard.html::select
- steps:
  1. A blocked gate reaches groom through one of the supported sources. A valid
     [blocked push payload](../blocked-push-payload.md) sent to [receive blocked push](../http/groom.md#receive-blocked-push)
     normalizes the workflow id and gate file path, hydrates Docker volume
     metadata when possible, upserts the workflow as blocked, and stores one
     [gate info](../concepts/gate-info.md) keyed by that file path. Startup or
     manual [workflow discovery scan](../concepts/workflow-discovery-scan.md)
     can also reconstruct the same visible blocked state from existing Docker
     and gate-file evidence, while the [sidecar blocked applier](../concepts/sidecar-blocked-applier.md)
     applies the persistent sidecar equivalent of the blocked delta.
  2. The blocked update renders a [dashboard shell fragment](../dashboard-shell-fragment.md)
     for the current [workflow registry](../concepts/workflow-registry.md) and
     enqueues it to connected dashboard client queues. Residual blocked pushes
     and sidecar blocked deltas append a [blocked notification script fragment](../blocked-notification-script-fragment.md)
     in the same websocket swap batch; browser execution dispatches
     `groom:blocked`, causing the dashboard to show the blocked toast and, when
     [browser notification permission](../concepts/browser-notification-permission.md)
     is granted, a system notification.
  3. The browser applies the shell frame through htmx out-of-band swaps. The
     [operator inbox](../operator-inbox.md) region is replaced with an
     [inbox worker row](../gui/screens/groom-dashboard.md#inbox-worker-row) for
     the gated workflow, sorted ahead of non-blocked gated workers, showing the
     workflow identity, gate file path, state dot, optional workflow type badge,
     and blocked-question preview. The status bar is replaced from the same
     snapshot; the selected worker detail pane is not part of this live shell
     update, so any half-typed answer in `#detail` is preserved.
  4. The operator activates the inbox row by pointer/tap or by global `j`/`k`
     row movement. [Select inbox worker row](../gui/screens/groom-dashboard.md#select-inbox-worker-row)
     stores the selected workflow id in browser state, reapplies the selected
     row class, and requests [GET /worker/{container_id}](../http/groom.md#get-worker-detail)
     with the row's `data-worker-id`.
  5. [Serve worker detail](../http/groom.md#serve-worker-detail) reads the
     selected [workflow container](../concepts/workflow-container.md) from the
     in-memory registry and returns one `#detail` fragment. For each open gate,
     the [worker detail renderer](../concepts/worker-detail-renderer.md) emits a
     gate block containing the escaped markdown question in a `data-md` text
     node, hidden `cmd=answer`, hidden `workflow_id`, hidden `file_path`, the
     [detail answer textarea](../gui/screens/groom-dashboard.md#detail-answer-textarea),
     and the [detail send answer button](../gui/screens/groom-dashboard.md#detail-send-answer-button).
  6. The operator enters answer text through [edit detail answer textarea](../gui/screens/groom-dashboard.md#edit-detail-answer-textarea).
     Text editing stays local to the browser form control; it does not send a
     websocket message, alter server state, or lose data during live inbox/status
     shell broadcasts because those broadcasts do not replace `#detail`.
  7. The operator activates [send detail answer](../gui/screens/groom-dashboard.md#send-detail-answer).
     The htmx websocket extension serializes the form fields into one
     [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md)
     with `cmd: "answer"`, the selected workflow id, the selected gate file path,
     and the textarea value, then sends that JSON object over the existing
     [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session).
  8. The dashboard websocket receive loop passes the decoded object to
     `_handle_command`. Non-`answer` commands are ignored. For an answer command,
     the handler string-normalizes `workflow_id`, `file_path`, and `answer`,
     looks up the workflow's current workspace volume, and calls the
     [gate-answering layer](../concepts/gate-answering-layer.md) with those four
     values.
  9. The [gate-answering layer](../concepts/gate-answering-layer.md) rejects an
     empty workspace volume before locking. Otherwise it obtains the
     [per-gate answer lock](../concepts/per-gate-answer-lock.md) for the
     `(container_id, file_path)` pair, rereads the current gate file through the
     [workspace volume file-content reader](../concepts/workspace-volume-file-content-reader.md),
     accepts only a current `AWAITING_OPERATOR` status, builds the answered text
     through [operator gate context file](../operator-gate-context-file.md#method-apply-answer),
     and writes it back through the [workspace volume file writer](../concepts/workspace-volume-file-writer.md).
  10. After a successful gate-file write, the gate-answering layer removes the
      matching in-memory gate through the [workflow gate clearer](../concepts/workflow-gate-clearer.md).
      It then checks whether the workflow container is still running through the
      [container running-state check](../concepts/container-running-state-check.md);
      a running container wakes in place from the changed file, while a stopped
      container receives exactly one [stopped container start fallback](../concepts/stopped-container-start-fallback.md)
      attempt. The layer returns an [answer result](../answer-result.md) whose
      `ok` flag means the gate-file write succeeded, even if the stopped
      restart fallback failed afterward.
  11. `_handle_command` records one [answer log entry](../answer-log-entry.md)
      in the process-local [answer event log](../concepts/answer-event-log.md)
      for every returned answer result. If the result succeeded, the workflow
      still exists, the answered gate was the last visible gate, and the workflow
      is still blocked, the handler applies the [successful last gate answer](../concepts/workflow-state.md#transition-successful-last-gate-answer)
      state transition to show the worker as running immediately.
  12. `_handle_command` renders a fresh [dashboard shell fragment](../dashboard-shell-fragment.md)
      for every expected answer result and broadcasts it to dashboard client
      queues. Successful results append a [groom answered script fragment](../groom-answered-script-fragment.md)
      after the shell fragment; expected failures broadcast only the shell
      fragment, leave the visible gate present, and emit no success event.
  13. Each dashboard tab applies the answer broadcast. The inbox and status bar
      converge on the post-answer workflow snapshot; if the answered gate was
      the workflow's last open gate, the worker disappears from the inbox and
      blocked counts decrease. Browser execution of the success-only script
      dispatches `groom:answered` with [groom answered browser event detail](../groom-answered-browser-event-detail.md),
      and the dashboard listener shows the `answer sent` toast.
  14. In the tab whose selected worker id still matches the answered event's
      `detail.id`, the `groom:answered` listener calls the same selected-worker
      path again, causing [GET /worker/{container_id}](../http/groom.md#get-worker-detail)
      to refresh `#detail`. The refreshed detail removes the answered gate block
      or shows the no-open-gate state. Tabs currently editing a different
      selected worker are not refetched, so their half-typed answers are not
      clobbered by another worker's answer success.
- end: the accepted answer is present in the workflow workspace gate file as
  `STATUS: ANSWERED` plus the stripped non-blank answer paragraph when supplied;
  groom's process-local gate map no longer contains that `(workflow, file_path)`
  gate; the workflow is displayed as running when its last gate cleared from a
  blocked state; every connected dashboard tab receives refreshed inbox/status
  shell data; successful answer submissions dispatch exactly one `groom:answered`
  event per broadcast and refetch only matching selected-worker detail panes.
  Failed, duplicate, stale, missing-volume, missing-file, or failed-write answer
  attempts instead record a failed answer result, broadcast a shell refresh
  without a success script, leave the gate visible, and do not refetch the
  selected detail through the answer-success handler.
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script,
  groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch,
  groom/tests/test_gates.py::test_answer_gate_rejects_when_already_answered,
  groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running,
  groom/tests/test_gates.py::test_answer_gate_restarts_when_container_stopped,
  groom/tests/test_gates.py::test_answer_gate_reports_missing_workspace_volume,
  groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form,
  groom/tests/test_render.py::test_render_answered_script_carries_worker_and_file,
  groom/tests/test_render.py::test_inbox_shows_only_workers_with_open_gates
