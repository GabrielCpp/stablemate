---
type: flow
slug: operator-answers-blocked-gate
title: Operator answers blocked gate
---
# Operator answers blocked gate

This journey covers the as-built operator path from a workflow becoming blocked,
through the [groom dashboard](../gui/screens/groom-dashboard.md) runs list and run
detail, to submitting the [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md)
over [WS /ws](../http/groom.md#websocket-dashboard), writing the answered
[operator gate context file](../operator-gate-context-file.md), pushing the run's
refreshed detail to the tabs watching it, and broadcasting the
[dashboard answered message](../dashboard-answered-message.md). The entry gate can
arrive from [receive blocked push](../http/groom.md#receive-blocked-push),
[workflow discovery scan](../concepts/workflow-discovery-scan.md), or the
[sidecar blocked applier](../concepts/sidecar-blocked-applier.md); once visible,
the answer path is the same open-run detail and websocket command flow.

Nothing on this path is markup. Every frame in it — the fleet, the run's detail, the
blocked alert, the answer confirmation — is JSON, and the browser renders it. That is
what lets the confirmation carry nothing but the toast: the detail push that travels
with the same command has already replaced the pane's gate list, so no tab re-fetches.

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
- code: groom/groom/projection.py::detail_message
- code: groom/groom/assets/dashboard.js::wireAnswerForm
- code: groom/groom/assets/dashboard.js::select
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
  2. The blocked update broadcasts a [dashboard state payload](../dashboard-state-payload.md)
     built from the current [workflow registry](../concepts/workflow-registry.md)
     to every connected dashboard client queue, and — because one named run is what
     changed — pushes that run's detail to the tabs watching it through the
     [run watch registry](../concepts/run-watch-registry.md). Both halves travel
     together: a gate opening changes the row *and* the pane the operator has open.
  3. Residual blocked pushes and sidecar blocked deltas additionally broadcast a
     one-shot `notify` frame carrying the workflow name and the question truncated
     to the [question notification limit](../concepts/groom-app-module.md#field-question-notify-limit).
     It is kept off the `state` frame deliberately, so it accompanies an actual new
     block rather than every reconciliation re-push. Each tab hands it to the
     [dashboard toast pusher](../concepts/dashboard-toast-pusher.md#method-on-notify),
     which shows the blocked toast and, when [browser notification permission](../concepts/browser-notification-permission.md)
     is granted, a system notification.
  4. Each tab applies the `state` frame through the one apply path the HTTP resync
     also uses. The [runs fleet view](../runs-fleet-view.md) island re-renders,
     showing a [run row](../gui/screens/groom-dashboard.md#run-row) for the gated
     workflow sorted ahead of non-blocked workers, with the workflow identity, state
     dot, optional type badge, and blocked-question preview; the status bar re-renders
     from the same snapshot. Rows are keyed by run id, so focus and scroll survive,
     and a tab that is not watching this run sees no detail change at all.
  5. The operator activates the run row by pointer/tap or by global `j`/`k`
     row movement. [Select run row](../gui/screens/groom-dashboard.md#select-run-row)
     stores the run id and a null detail in one store write, sends this tab's watch
     subscription for that run over the socket, and requests
     [GET /worker/{container_id}](../http/groom.md#get-run-detail) once so the pane
     is filled immediately rather than up to a tick later.
  6. [Serve run detail](../http/groom.md#serve-run-detail) reads the selected
     [workflow container](../concepts/workflow-container.md) from the in-memory
     registry and returns the same JSON body the socket pushes. For each open gate it
     carries the gate's file path and its question **as data, not markup**; the
     client renders the markdown and sanitizes it before it reaches the document, and
     builds the form around it: hidden `cmd=answer`, hidden `workflow_id`, hidden
     `file_path`, the [detail answer textarea](../gui/screens/groom-dashboard.md#detail-answer-textarea),
     and the [detail send answer button](../gui/screens/groom-dashboard.md#detail-send-answer-button).
  7. The operator enters answer text through [edit detail answer textarea](../gui/screens/groom-dashboard.md#edit-detail-answer-textarea).
     Text editing stays local to the browser form control: no input handler, no draft
     in the store, no websocket message. It survives every subsequent push because the
     gate block is keyed by gate file path, so the reconciler reuses the same
     `<textarea>` DOM node rather than replacing it.
  8. The operator activates [send detail answer](../gui/screens/groom-dashboard.md#send-detail-answer).
     The client's own submit handler prevents the browser's navigation, serializes the
     form fields into one [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md)
     with `cmd: "answer"`, the selected workflow id, the selected gate file path,
     and the textarea value, then sends that JSON object over the existing
     [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session).
     Because the client serializes the frame itself, a refused send is observable: the
     textarea keeps its text and a `✗ not sent` toast says the connection is gone.
  9. The dashboard websocket receive loop passes the decoded object to
     `_handle_command`. Unrecognized commands are ignored. For an answer command,
     the handler string-normalizes `workflow_id`, `file_path`, and `answer`,
     looks up the workflow's current workspace volume, and calls the
     [gate-answering layer](../concepts/gate-answering-layer.md) with those values
     plus whether the run is native rather than containerized.
  10. The [gate-answering layer](../concepts/gate-answering-layer.md) rejects an
      empty workspace volume before locking. Otherwise it obtains the
      [per-gate answer lock](../concepts/per-gate-answer-lock.md) for the
      `(container_id, file_path)` pair, rereads the current gate file through the
      [workspace volume file-content reader](../concepts/workspace-volume-file-content-reader.md),
      accepts only a current `AWAITING_OPERATOR` status, builds the answered text
      through [operator gate context file](../operator-gate-context-file.md#method-apply-answer),
      and writes it back through the [workspace volume file writer](../concepts/workspace-volume-file-writer.md).
  11. After a successful gate-file write, the gate-answering layer removes the
      matching in-memory gate through the [workflow gate clearer](../concepts/workflow-gate-clearer.md).
      It then checks whether the workflow container is still running through the
      [container running-state check](../concepts/container-running-state-check.md);
      a running container wakes in place from the changed file, while a stopped
      container receives exactly one [stopped container start fallback](../concepts/stopped-container-start-fallback.md)
      attempt. The layer returns an [answer result](../answer-result.md) whose
      `ok` flag means the gate-file write succeeded, even if the stopped
      restart fallback failed afterward.
  12. `_handle_command` records one [answer log entry](../answer-log-entry.md)
      in the process-local [answer event log](../concepts/answer-event-log.md)
      for every returned answer result. If the result succeeded, the workflow
      still exists, the answered gate was the last visible gate, and the workflow
      is still blocked, the handler applies the [successful last gate answer](../concepts/workflow-state.md#transition-successful-last-gate-answer)
      state transition to show the worker as running immediately.
  13. `_handle_command` broadcasts a fresh [dashboard state payload](../dashboard-state-payload.md)
      for every expected answer result, and pushes that run's refreshed detail —
      gates included — to the tabs watching it. On success only, it also broadcasts a
      [dashboard answered message](../dashboard-answered-message.md) naming the run and
      the answered gate file. Expected failures broadcast the state frame alone, leave
      the visible gate present, and emit no success event.
  14. Each dashboard tab applies the broadcast. The runs list and status bar
      converge on the post-answer snapshot; if the answered gate was the workflow's
      last open gate, the run leaves the blocked group and blocked counts decrease.
      The tabs *watching* that run receive the detail push and re-render the pane
      without the answered gate — nobody re-fetches. The answered message carries only
      the confirmation, which the [dashboard toast pusher](../concepts/dashboard-toast-pusher.md#method-on-answered)
      shows as `✓ answer sent`; a tab holding a half-typed answer against a different
      run is untouched, because the frame that would change a pane is addressed to
      watchers of one run and this one changes no pane at all.
- end: the accepted answer is present in the workflow workspace gate file as
  `STATUS: ANSWERED` plus the stripped non-blank answer paragraph when supplied;
  groom's process-local gate map no longer contains that `(workflow, file_path)`
  gate; the workflow is displayed as running when its last gate cleared from a
  blocked state; every connected dashboard tab receives a refreshed state payload
  and every tab watching the answered run receives its refreshed detail; successful
  answer submissions broadcast exactly one answered message per answer.
  Failed, duplicate, stale, missing-volume, missing-file, or failed-write answer
  attempts instead record a failed answer result, broadcast a state refresh
  without an answered message, and leave the gate visible in both the list and
  every open pane.
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_an_answered_event,
  groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch,
  groom/tests/test_app.py::test_watch_registers_the_tab_and_pushes_that_run_immediately,
  groom/tests/test_app.py::test_a_detail_push_reaches_only_the_tabs_watching_that_run,
  groom/tests/test_gates.py::test_answer_gate_rejects_when_already_answered,
  groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running,
  groom/tests/test_gates.py::test_answer_gate_restarts_when_container_stopped,
  groom/tests/test_gates.py::test_answer_gate_reports_missing_workspace_volume,
  groom/tests/test_projection.py::test_gate_question_travels_as_data_not_markup,
  groom/tests/test_projection.py::test_run_detail_lists_every_open_gate,
  groom/tests/test_a11y_dynamic.py::test_the_answer_form_is_reachable_and_submittable_by_keyboard
