---
type: concept
slug: invoke-claude
title: _invoke_claude — the transient-retry/cap-wait invocation layer
---
# _invoke_claude — the transient-retry/cap-wait invocation layer

The layer [_invoke_and_parse](invoke-and-parse.md) calls to run **one agent-CLI turn** through the
selected [`AgentBackend`](agent-backend.md) (`backend.run_turn`). This is Layer 1 of
[run_agent](run-agent.md)'s [ladder](run-agent.md#the-ladder) — the *only* layer that retries a
`BackendInvocationError` without giving up the in-flight session or the node's prompt: it absorbs
short transient failures with exponential backoff and rides out scheduled-reset caps by sleeping
until the window reopens, surfacing only invocation failures the backend itself can't recover from
(non-transient errors, and transient errors once their own retry budget is spent) to its caller.

- code: `workhorse/workhorse/runner/agent.py::_invoke_claude`
- verify: `workhorse/tests/test_agent_cap.py::test_cap_hang_pauses_then_resumes_same_node`,
  `workhorse/tests/test_agent_cap.py::test_structured_reset_at_drives_invoke_wait`,
  `workhorse/tests/test_agent_cap.py::test_budget_timeout_warns_retry_with_time_budget`,
  `workhorse/tests/test_agent_cap.py::test_non_timeout_transient_retries_prompt_unchanged`,
  `workhorse/tests/test_agent_cap.py::test_cap_waits_do_not_consume_short_retry_budget`,
  `workhorse/tests/test_agent_cap.py::test_cap_wait_safety_bound`,
  `workhorse/tests/test_agent_cap.py::test_short_transient_uses_bounded_backoff_then_fails`,
  `workhorse/tests/test_agent_cap.py::test_non_transient_fails_immediately`

## Contract

- **Input:**
  - `prompt: str` — the prompt for this call's first attempt.
  - `node_id: str` — the workflow node this turn belongs to (logging only).
  - `session_id_path: Path | None` — forwarded unchanged to `backend.run_turn` on every attempt, so
    every retry in this loop resumes the same session.
  - `model: str | None`, `effort: str | None`, `cwd: str | None`, `add_dirs: list[str] | None` —
    forwarded unchanged to `backend.run_turn` on every attempt.
  - `backend: AgentBackend | None` (default `None`) — the harness to invoke; when omitted,
    [`get_backend()`](get-backend.md) resolves the run's configured CLI (`--cli`/`AGENT_CLI`).
  - `max_invoke_retries: int` (default `DEFAULT_MAX_INVOKE_RETRIES`, env `AGENT_MAX_INVOKE_RETRIES`,
    default `4`) — additional short-transient attempts after the first, before giving up.
  - `timeout: float` (default `DEFAULT_RESULT_TIMEOUT_S`) — the per-turn wall-clock budget passed to
    `backend.run_turn`.
- **Output:** `str` — the turn's result text, as classified/returned by `backend.run_turn`
  (`classify_turn` under the hood for the Claude backend).
- **Raises:** `BackendInvocationError` — re-raised once a failure is non-`transient`
  ([`overflow`](classify-turn.md#backendinvocationerror) included — this loop only retries
  short-transient and cap failures, never overflow), or once the short-transient budget
  (`max_invoke_retries`) or the cap-wait budget (`_MAX_CAP_WAITS`, env `AGENT_MAX_CAP_WAITS`,
  default `48`) is exhausted.

## Algorithm

```
short_attempt = 0
cap_waits = 0
attempt_prompt = prompt
while True:
    try:
        return backend.run_turn(attempt_prompt, node_id, session_id_path, model, timeout,
                                 cwd, add_dirs, effort)
    except BackendInvocationError as exc:
        if not exc.transient:
            raise
        is_cap_hit = exc.reset_at is not None or _is_cap(str(exc))
        if exc.timed_out and not is_cap_hit:
            attempt_prompt = _timeout_retry_prompt(prompt, timeout)   # warn the retry of its budget
        else:
            attempt_prompt = prompt                                  # unchanged
        if is_cap_hit:
            if cap_waits >= _MAX_CAP_WAITS: raise
            cap_waits += 1
            delay, when = _cap_delay_seconds(exc)
            _sleep_with_notice(delay, node_id, "cap reset")
            continue
        if short_attempt >= max_invoke_retries: raise
        delay = min(_INVOKE_BACKOFF_BASE_S * (2 ** short_attempt), _INVOKE_BACKOFF_CAP_S)
        short_attempt += 1
        time.sleep(delay)
```

1. **Invoke.** Resolve `backend` via [`get_backend()`](get-backend.md) if not supplied, then call
   `backend.run_turn(attempt_prompt, ...)`. Success returns the result text immediately.
2. **Non-transient → re-raise immediately.** A `BackendInvocationError` with `transient=False`
   (including `overflow=True`, a crashed CLI, or a deterministic non-zero exit — see
   [`classify_turn`](classify-turn.md#backendinvocationerror)) is not this loop's job; it propagates
   to the caller ([`run_agent`](run-agent.md#the-ladder)'s compact/reframe layers).
3. **Classify the transient failure as a cap or a short blip.** `is_cap_hit = exc.reset_at is not
   None or _is_cap(str(exc))` — a structured `reset_at` (from Claude's `rate_limit_event`) or a
   cap-marker substring match (`_CAP_MARKERS`, the same predicate `classify_turn` uses) identifies a
   *scheduled-reset* cap versus a short transient (rate limit, overload, network blip).
4. **Decide the retry prompt.** If the failure carries `timed_out=True` *and* is not a cap (a cap
   can also set `timed_out=True` when the CLI hangs, but must not get this treatment — the model
   never ran; the cap cleared externally), the retry prompt is
   [`_timeout_retry_prompt(prompt, timeout)`](#related-pieces): it prepends a warning that the prior
   attempt was killed for overrunning its wall-clock budget and names the same budget so the retry
   can size its work to fit. Every other transient retries the **original** `prompt` unchanged.
5. **A cap hit sleeps until the window reopens, uncapped by the short-retry budget.** Bounded only
   by `_MAX_CAP_WAITS` (default 48) consecutive waits — not `max_invoke_retries`, and not by any
   exponential backoff — because a cap always eventually clears; retrying sooner can't help.
   [`_cap_delay_seconds(exc)`](cap-delay-seconds.md) computes how long to sleep (preferring the
   structured `reset_at` epoch, else parsing "resets HH:MMam" from the message, else a default) and
   a human-readable "resuming around" label; [`_sleep_with_notice`](sleep-with-notice.md) sleeps
   that duration, printing a "still paused" line periodically so a long, legitimate wait isn't
   mistaken for a hang. The loop then `continue`s — same session, same (unchanged) prompt.
6. **A short transient backs off exponentially, bounded by `max_invoke_retries`.** Once exhausted,
   the last `BackendInvocationError` is re-raised. Otherwise sleep
   `min(_INVOKE_BACKOFF_BASE_S * 2**short_attempt, _INVOKE_BACKOFF_CAP_S)` (env
   `AGENT_INVOKE_BACKOFF_BASE_S`/`AGENT_INVOKE_BACKOFF_CAP_S`, defaults 15s/300s) and loop back to
   step 1 with the (possibly budget-warned) `attempt_prompt`.

Cap waits and short-transient retries are tracked by **separate counters** (`cap_waits`,
`short_attempt`) and neither consumes the other's budget — a run can wait out many caps in a row
without ever touching its short-retry allowance, and vice versa.

## Related pieces

- [`AgentBackend.run_turn`](agent-backend.md#contract) / [`get_backend`](get-backend.md) — the
  backend abstraction and selector this function invokes each attempt; for the `claude` backend,
  `run_turn` is `_run_claude_cli`, which streams the CLI and classifies the result via
  [`classify_turn`](classify-turn.md).
- [`classify_turn`](classify-turn.md) / [`BackendInvocationError`](classify-turn.md#backendinvocationerror)
  — the shared classifier and error type this loop's `except` branches on (`transient`, `overflow`,
  `timed_out`, `reset_at`).
- `_is_cap` — the cap-marker substring predicate, shared with `classify_turn` (see
  [classify-turn.md](classify-turn.md#related-pieces)); not yet modeled as its own concept node.
- [`_cap_delay_seconds`](cap-delay-seconds.md) — computes the cap-wait duration and its
  "resuming around" label. [`_sleep_with_notice`](sleep-with-notice.md) — performs the
  periodically-announced sleep.
- [`_timeout_retry_prompt`](timeout-retry-prompt.md) — the budget-overrun warning prepended to a
  retry after a genuine wall-clock timeout; one of the three prompt-mutation strategies (see
  [rephrase-prompt.md](rephrase-prompt.md#related-pieces)).
- [`_invoke_and_parse`](invoke-and-parse.md) — the caller; invokes this function once per
  output-retry attempt, all against the same `session_id_path`.
- [`run_agent`](run-agent.md) — two levels up; its [ladder](run-agent.md#the-ladder) is what a
  non-transient or retry-exhausted `BackendInvocationError` from this function ultimately feeds.
