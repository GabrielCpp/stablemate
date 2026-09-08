---
type: concept
slug: jsonl-backend
title: JsonlBackend — shared NDJSON backend base
---
# JsonlBackend — shared NDJSON backend base

The shared transport boundary for backends whose CLI emits newline-delimited JSON. It separates
the provider event vocabulary from the supervised process stream: a concrete adapter supplies an
`OnEvent` callback and a command, while [`stream_jsonl`](stream-jsonl.md) parses each output line,
accumulates a [`TurnState`](finalize-turn.md#turnstate), and returns the process outcome. The
abstract `JsonlBackend` stores that stream as an instance dependency; concrete adapters still own
their command construction, event vocabulary, and [`finalize_turn`](finalize-turn.md) call. The
module's public contract consists of the `OnEvent` and `JsonlStream` callback protocols, the
`stream_jsonl` implementation, and the `JsonlBackend` base class. Its four current subclasses are
[`CodexBackend`](codex-backend.md), [`CopilotBackend`](copilot-backend.md),
[`ClineBackend`](cline-backend.md), and [`OpenCodeBackend`](opencode-backend.md).

- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend`
- extends: [AgentBackend](agent-backend.md)
- tests: `workhorse/tests/test_backends.py::_fake_stream`,
  `workhorse/tests/test_backends.py::test_codex_run_turn_fresh_then_resume`,
  `workhorse/tests/test_backends.py::test_opencode_cap_log_line_aborts_stream_early`,
  `workhorse/tests/test_backends.py::test_opencode_cap_structured_error_event_aborts_stream_early`,
  `workhorse/tests/test_backends.py::test_opencode_provider_header_timeout_aborts_into_short_retry`

The module has no provider-specific schema. Parsed JSON is passed unchanged to `OnEvent`; an
unknown event is therefore the adapter's responsibility, while malformed output is retained by
the shared stream as a diagnostic. A callback or test double is stored on each backend instance,
so separate backend turns do not depend on a module-global stream implementation. `JsonlStream` is
the substitution port for the live subprocess boundary: production backends default to
`stream_jsonl`, while tests can inject a callable that records the constructed command and returns
a canned `TurnState`.

## Methods

### __init__
- sig: `__init__(stream: JsonlStream = stream_jsonl) -> None`
- does: stores the supplied stream callable on the backend instance
- returns: `None`
- verify: emitted(event="injected JSONL stream invocation", count=1)
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend.__init__`

### stream_jsonl
- sig: `stream_jsonl(cmd: list[str], node_id: str, timeout: float, stdin_data: str | None, on_event: OnEvent, *, resilience: AgentResilience, cwd: str | None = None, env_extra: dict[str, str] | None = None) -> TurnState`
- does: runs the command through the supervised subprocess stream with the supplied timeout, resilience policy, working directory, and extra environment
- does: dispatches each non-empty line that parses as a JSON object to `on_event(event, state, node_id)`
- does: echoes each non-JSON line with the node prefix and retains its stripped text in `state.diagnostics`
- does: requests an early stream abort when newly-added diagnostics identify a spending cap or transient provider failure
- does: marks the returned state timed out when the subprocess stream times out or an early abort occurs
- returns: the completed `TurnState` with accumulated result text, session id, usage, diagnostics, timeout state, and child return code
- verify: emitted(event="supervised JSONL subprocess stream", count=1)
- verify: count(subject="parsed JSON objects dispatched to the event callback", equals=1)
- verify: json_path(path="$.diagnostics[0]", matches="^diagnostic line$")
- verify: emitted(event="JSONL early abort", count=1)
- verify: json_path(path="$.timed_out", equals=true)
- verify: json_path(path="$.returncode", equals=0)
- code: `workhorse/workhorse/runner/backends/jsonl.py::stream_jsonl`

### OnEvent.__call__
- sig: `__call__(event: dict[str, Any], state: TurnState, node_id: str) -> None`
- abstract: `true`
- does: accepts one already-parsed provider event without imposing a provider schema
- does: folds provider-specific result, session, usage, or diagnostic data into the shared turn state
- returns: `None`
- verify: emitted(event="provider event folded into turn state", count=1)
- code: `workhorse/workhorse/runner/backends/jsonl.py::OnEvent.__call__`
- tests: `workhorse/tests/test_backends.py::test_codex_on_event_extracts_text_and_session`,
  `workhorse/tests/test_backends.py::test_opencode_on_event_text_session_and_error`

### JsonlStream.__call__
- sig: `__call__(cmd: list[str], node_id: str, timeout: float, stdin_data: str | None, on_event: OnEvent, *, resilience: AgentResilience, cwd: str | None = None, env_extra: dict[str, str] | None = None) -> TurnState`
- abstract: `true`
- does: provides one supervised NDJSON turn stream to a JSONL backend using the command, input, callback, resilience policy, directory, and environment supplied by the caller
- does: returns a `TurnState` so the backend can classify result text, session identity, usage, diagnostics, timeout state, and return code
- returns: the resulting `TurnState`
- verify: emitted(event="supervised JSONL stream", count=1)
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlStream.__call__`
- tests: `workhorse/tests/test_backends.py::_fake_stream`,
  `workhorse/tests/test_backends.py::test_codex_run_turn_fresh_then_resume`

## Fields

### stream
- type: `JsonlStream`
- default: `stream_jsonl`
- required: true
- semantics: callable used by each JSONL backend turn to supervise its CLI process and accumulate a `TurnState`
- verify: emitted(event="injected JSONL stream invocation", count=1)
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend`

## Processing Rules

1. Create an empty `TurnState` and an empty early-abort marker.
2. For each raw line, strip whitespace and ignore an empty result.
3. Parse non-empty content as JSON. Parsed objects go to `on_event`; malformed content is printed as
   `[{node_id}] {line}` and appended to diagnostics.
4. Compare only diagnostics appended while handling that line. A cap marker wins over a transient
   marker; either marker stops the subprocess stream so the recovery ladder can act immediately.
5. Return the stream's child return code and combine its timeout result with the early-abort marker.

`JsonlBackend` remains abstract: its constructor only installs `stream`; subclasses implement
`AgentBackend.run_turn` and `compact`. The default is the production `stream_jsonl` function, but
callers may provide any callable satisfying `JsonlStream`.
