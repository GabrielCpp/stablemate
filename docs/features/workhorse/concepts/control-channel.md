---
type: concept
slug: control-channel
title: Control channel
---
# Control channel

The control channel is the live-run operator transport. A run owns one local Unix socket for
its lifetime; each client connection carries one JSON request and one JSON reply. Queries are
answered inside the wait loop, while actions are delivered to the waiting site that owns the
policy for ending or deferring the wait. The transport is bounded and fail-soft: malformed or
oversized requests are ignored by the run, and a missing listener is reported to the operator.

- code: `workhorse/workhorse/control.py::ControlChannel`
- tests: `workhorse/tests/test_control_channel.py::test_a_message_sent_to_a_live_run_arrives_with_its_reply`
- detail: [operator gate file](../operator-gate-file.md)

The CLI uses `Request` actions `reload`, `status`, `questions`, `answer`, and the switch
actions. `path` identifies an operator gate and `body` carries its answer; `core`,
`at_boundary`, `cli`, and `profile` carry reload and selection choices. `status` and `questions`
do not end a wait. `answer` is persisted by the gate consumer before it is acknowledged.

## Fields

### action
- type: string
- default: `reload`
- required: true
- semantics: request verb
- verify: json_path(path="$.action", matches=".+")
- semantics: unknown verbs remain deliverable to the consumer
- verify: count(subject="unknown action requests delivered to consumers", equals=1)
- semantics: unknown verbs are declined by the consumer
- verify: count(subject="unknown action requests declined by the consumer", equals=1)
- code: `workhorse/workhorse/control.py::Request`
- detail: [request field selection](request-field-selection.md)

### core
- type: boolean
- default: `false`
- required: true
- semantics: reload workhorse itself as well as the workflow package
- verify: json_path(path="$.core", equals=false)
- code: `workhorse/workhorse/control.py::Request`
- detail: [request field selection](request-field-selection.md)

### at_boundary
- type: boolean
- default: `false`
- required: true
- semantics: defer reload until the next state boundary instead of cutting the active turn
- verify: json_path(path="$.at_boundary", equals=false)
- code: `workhorse/workhorse/control.py::Request`
- detail: [request field selection](request-field-selection.md)

### cli
- type: string
- default: empty string
- required: true
- semantics: agent CLI requested for a core reload
- verify: json_path(path="$.cli", matches=".+")
- semantics: empty means retain the current CLI
- verify: json_path(path="$.cli", equals="")
- code: `workhorse/workhorse/control.py::Request`
- detail: [request field selection](request-field-selection.md)

### profile
- type: string
- default: empty string
- required: true
- semantics: named model profile to apply from the next turn
- verify: json_path(path="$.profile", equals="")
- code: `workhorse/workhorse/control.py::Request`
- detail: [request field selection](request-field-selection.md)

### path
- type: string
- default: empty string
- required: true
- semantics: absolute operator-gate path targeted by an answer
- verify: json_path(path="$.path", equals="")
- code: `workhorse/workhorse/control.py::Request`
- detail: [request field selection](request-field-selection.md)

### body
- type: string
- default: empty string
- required: true
- semantics: operator prose delivered as an answer
- verify: json_path(path="$.body", equals="")
- code: `workhorse/workhorse/control.py::Request`
- detail: [request field selection](request-field-selection.md)

### requested_at
- type: string
- default: current UTC timestamp when serialized
- required: true
- semantics: timestamp attached to the wire request
- verify: json_path(path="$.requested_at", matches=".+")
- code: `workhorse/workhorse/control.py::Request`
- detail: [request field selection](request-field-selection.md)

## Methods

### cuts_the_turn
- sig: `Request.cuts_the_turn() -> bool`
- does: returns false only when at_boundary requests deferral
- returns: whether the active turn should be interrupted
- verify: count(subject="default reload requests that cut the turn", equals=1)
- code: `workhorse/workhorse/control.py::Request.cuts_the_turn`
- tests: `workhorse/tests/test_reload_request.py::test_the_default_request_cuts_the_turn`

### to_json
- sig: `Request.to_json() -> str`
- does: serializes all request fields as one JSON object
- returns: newline-free JSON text
- verify: json_path(path="$.action", equals="answer")
- code: `workhorse/workhorse/control.py::Request.to_json`
- tests: `workhorse/tests/test_control_channel.py::test_the_answer_fields_survive_the_wire`

### from_raw
- sig: `Request.from_raw(raw: object) -> Request | None`
- does: accepts an object, applies defaults, and drops unknown keys
- returns: a Request for an object, or None for a non-object
- verify: json_path(path="$.path", equals="")
- code: `workhorse/workhorse/control.py::Request.from_raw`
- tests: `workhorse/tests/test_control_channel.py::test_a_client_that_never_heard_of_the_answer_fields_still_parses`

### wait_until
- sig: `wait_until(predicate, *, timeout, clock, channel, tick) -> Request | None`
- does: checks the predicate before waiting and wakes for a control request
- returns: the request that ended the wait, or None for predicate completion or timeout
- verify: count(subject="control requests returned before a long timeout", equals=1)
- code: `workhorse/workhorse/control.py::wait_until`
- tests: `workhorse/tests/test_control_channel.py::test_a_request_ends_a_wait_that_had_hours_left`

### send
- sig: `send(run_dir, request, *, timeout=5.0) -> dict[str, object]`
- does: sends one newline-framed request and reads one reply
- raises: FileNotFoundError when no listener exists
- raises: ControlProtocolError when the reply exceeds REPLY_LIMIT
- verify: count(subject="control replies from a missing listener", equals=0)
- returns: a decoded reply object, or an empty dict for an unusable reply
- code: `workhorse/workhorse/control.py::send`
- tests: `workhorse/tests/test_control_channel.py::test_asking_a_run_that_is_not_running_says_so_immediately`

### arm
- sig: `arm(channel: ControlChannel | None) -> None`
- does: installs one channel and clears held requests
- does: disarming clears status and pending-question reporters
- verify: absent(subject="the previous run's status reporter after disarm")
- code: `workhorse/workhorse/control.py::arm`
- tests: `workhorse/tests/test_control_channel.py::test_disarming_forgets_how_the_last_run_described_itself`

### report_with
- sig: `report_with(describe: Callable[[], dict[str, object]] | None) -> None`
- does: registers the live status description used by status queries
- does: clears the reporter when passed None
- verify: visible(locator="status reply", text="Qa.plan_story")
- code: `workhorse/workhorse/control.py::report_with`
- tests: `workhorse/tests/test_control_channel.py::test_status_is_answered_under_every_wait_and_ends_none_of_them`

### questions_with
- sig: `questions_with(pending: Callable[[], list[dict[str, object]]] | None) -> None`
- does: registers the current pending-gate description used by questions queries
- does: returns an empty question list when no reporter is registered
- verify: count(subject="pending questions for an unattached run", equals=0)
- code: `workhorse/workhorse/control.py::questions_with`
- tests: `workhorse/tests/test_control_channel.py::test_a_run_blocked_on_nothing_answers_an_empty_list`

### armed
- sig: `armed() -> ControlChannel`
- returns: the installed channel, or NULL_CHANNEL when no run is attached
- verify: absent(subject="selectable control file descriptor after disarm")
- code: `workhorse/workhorse/control.py::armed`
- tests: `workhorse/tests/test_reload_request.py::test_a_run_that_ended_leaves_nothing_armed`

### take
- sig: `take() -> Request | None`
- does: delivers the next action request while answering status and questions in place
- returns: None when no actionable request is pending
- verify: count(subject="action requests delivered after a status query", equals=1)
- code: `workhorse/workhorse/control.py::take`
- tests: `workhorse/tests/test_control_channel.py::test_status_is_answered_under_every_wait_and_ends_none_of_them`

### outstanding
- sig: `outstanding() -> Request | None`
- does: returns a held request before reading the channel
- returns: None when no held or actionable request exists
- verify: count(subject="one held request consumed at the boundary", equals=1)
- code: `workhorse/workhorse/control.py::outstanding`
- tests: `workhorse/tests/test_reload_request.py::test_an_at_boundary_request_is_held_for_the_boundary_not_dropped`

### hold
- sig: `hold(request: Request) -> None`
- does: stores a deferred request for the next authorized consumer
- verify: count(subject="deferred requests available to the boundary", equals=1)
- code: `workhorse/workhorse/control.py::hold`
- tests: `workhorse/tests/test_reload_request.py::test_an_at_boundary_request_is_held_for_the_boundary_not_dropped`

### answer
- sig: `answer(payload: dict[str, object]) -> None`
- does: sends a best-effort reply on the armed channel
- verify: count(subject="replies delivered for a cutting reload", equals=1)
- code: `workhorse/workhorse/control.py::answer`
- tests: `workhorse/tests/test_reload_request.py::test_the_default_request_cuts_the_turn`

### SocketChannel
- sig: `SocketChannel.open(run_dir) -> SocketChannel`
- does: binds a 0600 AF_UNIX listener in the run directory or a digest-keyed temporary path
- raises: OSError when another process is already listening for the run directory
- verify: created(subject="live run control socket")
- code: `workhorse/workhorse/control.py::SocketChannel`
- tests: `workhorse/tests/test_control_channel.py::test_a_message_sent_to_a_live_run_arrives_with_its_reply`

### NullChannel
- sig: `NullChannel() -> ControlChannel`
- does: provides no selectable descriptor and never delivers a request
- verify: absent(subject="control file descriptor for a null channel")
- code: `workhorse/workhorse/control.py::NullChannel`
- tests: `workhorse/tests/test_control_channel.py::test_a_wait_with_no_channel_still_sleeps_through_its_clock`

### FakeChannel
- sig: `FakeChannel(*requests: Request) -> ControlChannel`
- does: delivers scripted requests and records replies without a socket
- verify: count(subject="scripted channel replies", equals=1)
- code: `workhorse/workhorse/control.py::FakeChannel`
- tests: `workhorse/tests/test_control_channel.py::test_status_is_answered_under_every_wait_and_ends_none_of_them`

### fileno
- sig: `ControlChannel.fileno() -> int | None`
- returns: a selectable listener descriptor, or None for an unattached/test channel
- verify: absent(subject="selectable descriptor for a null control channel")
- code: `workhorse/workhorse/control.py::ControlChannel.fileno`

### take
- sig: `ControlChannel.take() -> Request | None`
- returns: one non-blocking request when the channel is ready, or None otherwise
- verify: count(subject="requests taken from a scripted control channel", equals=1)
- code: `workhorse/workhorse/control.py::ControlChannel.take`

### reply
- sig: `ControlChannel.reply(payload: dict[str, object]) -> None`
- does: delivers a best-effort reply for the most recently accepted socket request
- verify: count(subject="reply records from a fake control channel", equals=1)
- code: `workhorse/workhorse/control.py::ControlChannel.reply`

### close
- sig: `ControlChannel.close() -> None`
- does: closes the channel and removes its socket discovery files
- verify: removed(subject="run control socket discovery files")
- code: `workhorse/workhorse/control.py::ControlChannel.close`
- tests: `workhorse/tests/test_control_channel.py::test_a_run_dir_too_long_for_sun_path_still_gets_a_channel`

### ControlProtocolError
- sig: `ControlProtocolError(message: str)`
- raises: when a newline-delimited control message exceeds its configured byte limit
- verify: count(subject="over-limit control messages rejected", equals=1)
- code: `workhorse/workhorse/control.py::ControlProtocolError`
- tests: `workhorse/tests/test_control_channel.py::test_a_message_over_its_limit_is_refused_rather_than_truncated`
