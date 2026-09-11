---
type: concept
slug: reload-policy
title: Reload policy
---
# Reload policy

Reload is a live-run control decision, not a failure or a new run. The streaming process cuts a
turn for the default request, while the state boundary handles deferred requests and requests
that arrived during deterministic work. A profile switch is queued and applied at a boundary;
it does not cut the current turn. A CLI switch is represented as a core reload because the CLI
is selected at the process edge.

- code: `workhorse/workhorse/reload.py::cut_by`
- tests: `workhorse/tests/test_reload_request.py::test_an_at_boundary_request_is_held_for_the_boundary_not_dropped`
- detail: [control channel](control-channel.md)

## Methods

### cut_requested
- sig: `cut_requested() -> Request | None`
- does: returns a reload request that should interrupt the active streaming turn
- returns: None for no request, deferred reloads, answers outside a gate wait, profile switches, and unknown actions
- verify: count(subject="default reload requests accepted by the streaming cut site", equals=1)
- code: `workhorse/workhorse/reload.py::cut_requested`
- tests: `workhorse/tests/test_reload_request.py::test_the_default_request_cuts_the_turn`

### cut_by
- sig: `cut_by(request: Request | None) -> Request | None`
- does: acknowledges and holds at-boundary reloads for the state boundary
- does: acknowledges profile switches as queued without cutting the active turn
- does: declines unknown actions and answers non-gate answers with an error
- returns: a cutting reload request, or None when the request is deferred or declined
- verify: count(subject="at-boundary reload requests held for later", equals=1)
- code: `workhorse/workhorse/reload.py::cut_by`
- tests: `workhorse/tests/test_reload_request.py::test_an_at_boundary_request_is_held_for_the_boundary_not_dropped`,
  `workhorse/tests/test_reload_reentry.py::test_an_unarmed_run_never_stops_at_a_boundary`

### boundary_requested
- sig: `boundary_requested() -> Request | None`
- does: returns a reload or profile switch outstanding at a state boundary
- does: acknowledges an at-boundary reload on the way past so the operator's CLI reports a delivered request rather than one that merely went out
- does: honours a held reload after the state checkpoint is on disk, so re-entry replays the state with the arguments it was bound with
- returns: None after a request has been consumed or declined
- verify: count(subject="one reload request consumed at one state boundary", equals=1)
- code: `workhorse/workhorse/reload.py::boundary_requested`
- tests: `workhorse/tests/test_reload_request.py::test_one_request_is_one_reload`,
  `workhorse/tests/test_reload_reentry.py::test_a_boundary_request_is_honoured_after_the_checkpoint_and_before_the_body`

### ReloadRequested
- sig: `ReloadRequested(message="reload requested", *, core=False, cli="")`
- does: unwinds nested drive frames without entering retry or failure handling
- does: closes one drive-frame scope per nesting level so a parent state span never outlives the run
- verify: count(subject="reload telemetry cuts for a reload exception", equals=1)
- returns: no terminal result
- verify: absent(subject="terminal result for the reload")
- returns: the driver re-enters from the durable checkpoint
- verify: persists(subject="the durable checkpoint for the re-entered run")
- code: `workhorse/workhorse/reload.py::ReloadRequested`
- tests: `workhorse/tests/test_reload_reentry.py::test_a_reload_raised_from_a_state_body_closes_that_states_span`,
  `workhorse/tests/test_reload_reentry.py::test_a_reload_deep_in_a_sub_flow_closes_one_scope_per_drive_frame`,
  `workhorse/tests/test_agent_recovery.py::test_a_reload_is_neither_retried_nor_reframed`,
  `workhorse/tests/test_agent_recovery.py::test_a_reload_during_compaction_is_not_read_as_compaction_being_unavailable`

## Fields

### RELOAD_EXIT_CODE
- type: integer
- semantics: process exit code requesting supervisor re-entry after a core reload cannot exec in place
- verify: json_path(path="$.reload_exit_code", equals=3)
- code: `workhorse/workhorse/reload.py::RELOAD_EXIT_CODE`
