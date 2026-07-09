---
type: concept
slug: finalize-turn
title: _finalize_turn — the shared turn-completion adapter
---
# _finalize_turn — the shared turn-completion adapter

The single call every non-Claude backend makes to turn a finished subprocess turn into a result or
a raised error: a thin, argument-renaming adapter over [`classify_turn`](classify-turn.md) so the
three JSONL backends (via [`_stream_jsonl`](stream-jsonl.md)) and the plain-text backend (via
[`_run_text_turn`](run-text-turn.md)) all classify through the exact same ladder the Claude path
(`_run_claude_cli`) uses, producing identical failure messages and transient/overflow/cap/
non-recoverable verdicts regardless of which CLI ran. It adds no classification logic of its own —
its only job is presenting each caller's already-collected turn state in `classify_turn`'s calling
convention.

- code: `workhorse/workhorse/runner/backends.py::_finalize_turn`
- verify: `workhorse/tests/test_backends.py::test_finalize_turn_classifies_failures`,
  `workhorse/tests/test_backends.py::test_finalize_turn_non_recoverable_names_each_backend`

## Contract

- **Input:**
  - `backend_name: str` — the CLI's registry name (`"codex"`, `"copilot"`, `"opencode"`, or
    [`"aider"`](aider-backend.md)), forwarded to `classify_turn` so its error messages name the
    right CLI.
  - `node_id: str` — the workflow node this turn belonged to, forwarded verbatim.
  - `state: dict` — the `{"result_text": ..., "session_id": ...}` mapping accumulated by the
    caller (`_stream_jsonl`'s `on_event` callbacks, or `_run_text_turn`'s joined transcript);
    `result_text` and `session_id` are read out of it with `.get(...)`.
  - `diagnostics` — the caller's collected non-result output (a newline-joined `str` from
    `_stream_jsonl`, or the same transcript text reused as diagnostics by `_run_text_turn`),
    forwarded to `classify_turn`'s `diagnostics` parameter unchanged.
  - `timed_out: bool` — whether the caller's own run (via
    [`stream_subprocess`](stream-subprocess.md)) timed out, was watchdog-killed, or hit an
    early cap-abort.
  - `returncode: int` — the subprocess's exit code, forwarded verbatim.
  - `session_id_path: Path | None` — where to persist `state["session_id"]` on success/overflow,
    forwarded verbatim.
  - `timeout: float` (default `_agent.DEFAULT_RESULT_TIMEOUT_S`) — the budget that was in effect,
    echoed into a timeout error message.
  - `rate_reset_at: float | None` (default `None`) — an out-of-band unix epoch for when a cap's
    window reopens (the opencode/Codex path's [`_codex_reset_at`](codex-reset-at.md) probe fetches
    this outside the event stream, since opencode drops the reset headers on its headless path);
    attached to the raised error so the runner sleeps until exactly then instead of the blind
    default wait.
- **Output:** `str` — the turn's result text on success, identical to what `classify_turn` returns.
- **Raises:** `agent.BackendInvocationError`, exactly as classified by `classify_turn` — this
  function adds no additional error paths.

## Algorithm

A single delegating call, no branching of its own:

```python
return _agent.classify_turn(
    backend_name, node_id,
    result_text=state.get("result_text"), diagnostics=diagnostics,
    timed_out=timed_out, returncode=returncode, timeout=timeout,
    session_id=state.get("session_id"), session_id_path=session_id_path,
    rate_reset_at=rate_reset_at,
)
```

`result_text`/`session_id` are pulled out of the caller's `state` dict; every other argument is
forwarded positionally/verbatim. `classify_turn` (not this function) owns every classification
rule — see its [ladder](classify-turn.md#ladder-first-match-wins).

## Related pieces

- [`classify_turn`](classify-turn.md) — the one function this adapter delegates to; owns every
  transient/overflow/cap/non-recoverable rule. `_finalize_turn` exists only so its three JSONL
  callers and the text-turn caller don't each reshape their own state into `classify_turn`'s
  signature independently.
- [`_stream_jsonl`](stream-jsonl.md) — calls this once per turn for `CodexBackend`,
  `CopilotBackend`, and `OpenCodeBackend`, immediately after its own read loop returns
  `(state, diagnostics, timed_out, returncode)`.
- [`_run_text_turn`](run-text-turn.md) — calls this once per turn for the aider backend, passing
  its joined transcript as both `state["result_text"]` and `diagnostics`.
- [`_codex_reset_at`](codex-reset-at.md) — `OpenCodeBackend.run_turn`'s out-of-band probe for the
  precise Codex-provider cap reset epoch, passed through as this function's `rate_reset_at` when
  the turn's diagnostics look like a cap.

