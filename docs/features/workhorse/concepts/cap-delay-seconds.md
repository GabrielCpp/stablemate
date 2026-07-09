---
type: concept
slug: cap-delay-seconds
title: _cap_delay_seconds — cap-wait duration
---
# _cap_delay_seconds — cap-wait duration

Computes how long [`_invoke_claude`](invoke-claude.md#algorithm) should sleep once it has
classified a `BackendInvocationError` as a scheduled-reset cap (`is_cap_hit`), plus a
human-readable "resuming around" label for the log line
[`_sleep_with_notice`](sleep-with-notice.md) prints. Prefers the structured
`reset_at` epoch the CLI attaches to the error (exact, timezone-correct) over parsing a reset
time out of the message text, and falls back to a fixed default when neither is available — the
cap always eventually clears, so a delay is always produced, never an error.

- code: `workhorse/workhorse/runner/agent.py::_cap_delay_seconds`
- verify: `workhorse/tests/test_agent_cap.py::test_cap_delay_prefers_structured_reset_at`,
  `workhorse/tests/test_agent_cap.py::test_cap_delay_falls_back_to_text_then_default`

## Contract

- **Input:**
  - `exc: BackendInvocationError` — the caught cap failure; only its
    [`reset_at`](classify-turn.md#backendinvocationerror) field and its `str(exc)` message text
    are read.
  - `now: float | None` (default `None`) — the current unix epoch to measure the structured
    `reset_at` against; `None` resolves to `time.time()`. Exposed as a parameter (rather than
    calling `time.time()` inline) purely so tests can pin "now" without patching the `time`
    module.
- **Output:** `tuple[float, str]` — `(delay_seconds, when_label)`: how long to sleep, and a
  label describing when the wait ends (or why it's short).
- **Raises:** nothing — every branch returns a value; there is no failure path.

## Algorithm

```
now = now if now is not None else time.time()
if exc.reset_at is not None:
    secs = exc.reset_at - now
    if secs > 0:
        delay = min(secs, _CAP_MAX_STRUCTURED_WAIT_S) + _CAP_WAIT_MARGIN_S
        when = datetime.fromtimestamp(now + delay).strftime("%a %H:%M")
        return delay, when
    return _CAP_WAIT_MARGIN_S, "reset already passed — retrying shortly"

parsed = _parse_reset_seconds(str(exc))
if parsed is None:
    return _CAP_DEFAULT_WAIT_S, "unknown reset — using default wait"
delay = parsed + _CAP_WAIT_MARGIN_S
return delay, (datetime.now() + timedelta(seconds=delay)).strftime("%a %H:%M")
```

1. **Resolve "now".** The `now` parameter wins when supplied (tests pin it); otherwise
   `time.time()`.
2. **Structured `reset_at` takes priority.** When `exc.reset_at` is set (the CLI's own
   `rate_limit_event.resetsAt`, attached by [`classify_turn`](classify-turn.md#ladder-first-match-wins)),
   compute `secs = exc.reset_at - now`:
   - **Still in the future (`secs > 0`).** The delay is `min(secs, _CAP_MAX_STRUCTURED_WAIT_S)` —
     bounded so a bogus far-future epoch (clock skew, a malformed event) can't stall the run for
     longer than `_CAP_MAX_STRUCTURED_WAIT_S` (env `AGENT_CAP_MAX_WAIT_S`, default `8 * 24 * 3600`
     = 8 days) — plus a fixed `_CAP_WAIT_MARGIN_S` (env `AGENT_CAP_WAIT_MARGIN_S`, default `120`)
     so the retry lands safely *after* the window reopens rather than racing it. The `when` label
     is computed from `now + delay` (the same base the caller passed in, not the real wall clock),
     formatted `"%a %H:%M"` (e.g. `"Tue 14:05"`).
   - **Already in the past (`secs <= 0`).** A stale event or clock skew — reset already happened,
     so there's nothing to wait out. Returns just the margin (`_CAP_WAIT_MARGIN_S`) as the delay,
     with a fixed label `"reset already passed — retrying shortly"` (no timestamp computed).
3. **No structured `reset_at` → parse the message text.**
   [`_parse_reset_seconds(str(exc))`](parse-reset-seconds.md#algorithm) looks for a reset clock-time
   embedded in the error string (e.g. `"resets 3:50am"`).
   - **Found.** `delay = parsed + _CAP_WAIT_MARGIN_S`; the label is computed from **real** wall-clock
     `datetime.now()` (not the `now` parameter — this branch never uses it) plus `delay`, formatted
     the same `"%a %H:%M"`.
   - **Not found.** Neither a structured epoch nor a parseable reset time — falls back to a fixed
     `_CAP_DEFAULT_WAIT_S` (env `AGENT_CAP_DEFAULT_WAIT_S`, default `3600` = 1 hour) with a fixed
     label `"unknown reset — using default wait"`.

Two of the four branches (structured-past, text-not-found) return a **fixed** label string instead
of a computed timestamp — the label always states either a concrete "resuming around" time or an
explicit reason none could be computed, never a bare number.

## Related pieces

- [`_invoke_claude`](invoke-claude.md#algorithm) — the sole caller; invokes this once per cap hit
  (`is_cap_hit`), then passes the returned `delay` to
  [`_sleep_with_notice`](sleep-with-notice.md) (which does the actual sleeping and periodic "still
  paused" logging) and discards the `when` label after logging it — `_invoke_claude` then
  `continue`s the same retry loop with the same session and prompt.
- [`BackendInvocationError.reset_at`](classify-turn.md#backendinvocationerror) — the structured
  signal this function prefers, set by [`classify_turn`](classify-turn.md#ladder-first-match-wins)
  from the CLI's `rate_limit_event.resetsAt` (via [`_rate_limit_info`](classify-turn.md#_rate_limit_info)).
- [`_parse_reset_seconds`](parse-reset-seconds.md#algorithm) — the text-parsing fallback this
  function calls when `exc.reset_at` is unset.
- [GUARDRAILS.md](../../../../workhorse/docs/GUARDRAILS.md) — documents the three env vars this
  function reads (`AGENT_CAP_MAX_WAIT_S`, `AGENT_CAP_WAIT_MARGIN_S`, `AGENT_CAP_DEFAULT_WAIT_S`) from
  an operator's perspective.

