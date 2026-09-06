---
type: concept
slug: jsonl-backend
title: JsonlBackend — shared NDJSON backend base
---
# JsonlBackend — shared NDJSON backend base

The abstract adapter base for backends whose CLI emits newline-delimited JSON. It owns an injected
stream callable so tests can capture argv or return a canned turn; concrete adapters still own
their command and event vocabulary. [`stream_jsonl`](stream-jsonl.md) creates the shared
[`TurnState`](finalize-turn.md#turnstate), and each adapter finishes it with
[`finalize_turn`](finalize-turn.md).

- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend`
- extends: [AgentBackend](agent-backend.md)
- tests: `workhorse/tests/test_backends.py::_fake_stream`,
  `workhorse/tests/test_backends.py::test_codex_run_turn_fresh_then_resume`

## Methods

### __init__
- sig: `__init__(stream: JsonlStream = stream_jsonl) -> None`
- does: stores the supplied stream callable on the instance for the adapter's turn execution
- returns: `None`
- verify: emitted(event="injected JSONL stream invocation", count=1)
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend.__init__`

### stream_jsonl
- sig: `stream_jsonl(cmd: list[str], node_id: str, timeout: float, stdin_data: str | None, on_event: OnEvent, *, resilience: AgentResilience, cwd: str | None = None, env_extra: dict[str, str] | None = None) -> TurnState`
- does: runs the command through the supervised subprocess stream and dispatches each parsed JSON object to `on_event`
- does: retains non-JSON lines as diagnostics and echoes them with the node prefix
- does: aborts and marks the state when a newly-added diagnostic identifies a cap or transient provider failure
- returns: a completed `TurnState` containing event results, diagnostics, timeout state, and child return code
- verify: emitted(event="JSONL turn state", count=1)

### OnEvent.__call__
- sig: `__call__(event: dict[str, Any], state: TurnState, node_id: str) -> None`
- does: folds one parsed provider event into the shared turn state
- returns: `None`
- verify: emitted(event="provider event folded into turn state", count=1)
- code: `workhorse/workhorse/runner/backends/jsonl.py::OnEvent.__call__`

### JsonlStream.__call__
- sig: `__call__(cmd: list[str], node_id: str, timeout: float, stdin_data: str | None, on_event: OnEvent, *, resilience: AgentResilience, cwd: str | None = None, env_extra: dict[str, str] | None = None) -> TurnState`
- does: provides one supervised NDJSON turn stream to a JSONL backend
- returns: the resulting `TurnState`
- verify: emitted(event="supervised JSONL stream", count=1)
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlStream.__call__`
- code: `workhorse/workhorse/runner/backends/jsonl.py::stream_jsonl`
