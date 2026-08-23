---
type: concept
slug: cap-delay-seconds
title: cap_delay_seconds — cap-wait duration
---
# cap_delay_seconds — cap-wait duration

Computes how long [`AgentRunner.turn`](agent-turn.md#algorithm) should sleep once it has
classified a `BackendInvocationError` as a scheduled-reset cap (`is_cap_hit`), plus a
human-readable "resuming around" label for the log line
[`sleep_with_notice`](sleep-with-notice.md) prints. Prefers the structured
`reset_at` epoch the CLI attaches to the error (exact, timezone-correct) over parsing a reset
time out of the message text, and falls back to a fixed default when neither is available — the
cap always eventually clears, so a delay is always produced, never an error.

- code: `workhorse/workhorse/runner/caps.py::cap_delay_seconds`
- verify: `workhorse/tests/test_agent_cap.py::test_cap_delay_prefers_structured_reset_at`,
  `workhorse/tests/test_agent_cap.py::test_cap_delay_falls_back_to_text_then_default`

## Contract

Public, and its two collaborators are keyword-only injections rather than module constants and a
call to `time.time()`. Nothing here reads the environment or the wall clock.

- **Input:**
  - `exc: BackendInvocationError` — the caught cap failure; only its
    [`reset_at`](classify-turn.md#backendinvocationerror) field and its `str(exc)` message text
    are read.
  - `resilience: AgentResilience` (keyword-only) — supplies `cap_max_wait_s`, `cap_wait_margin_s`
    and `cap_default_wait_s`. These were loose module constants read from the environment at
    import time; they are fields on the run's resilience policy now, so a test states a bound
    instead of setting an env var.
  - `clock: Clock` (keyword-only) — "now" comes from `clock.now()`, a `datetime`. Both the
    structured and the text-parsing path read it, so a cap that reopens eight hours out is a test
    that states the hour rather than one that patches `time`.
- **Output:** `tuple[float, str]` — `(delay_seconds, when_label)`: how long to sleep, and a
  label describing when the wait ends (or why it's short).
- **Raises:** nothing — every branch returns a value; there is no failure path.

## Algorithm

```
now = clock.now()
if exc.reset_at is not None:
    secs = exc.reset_at - now.timestamp()
    if secs > 0:
        delay = min(secs, resilience.cap_max_wait_s) + resilience.cap_wait_margin_s
        when = (now + timedelta(seconds=delay)).strftime("%a %H:%M")
        return delay, when
    return resilience.cap_wait_margin_s, "reset already passed — retrying shortly"

parsed = parse_reset_seconds(str(exc), now)
if parsed is None:
    return resilience.cap_default_wait_s, "unknown reset — using default wait"
delay = parsed + resilience.cap_wait_margin_s
return delay, (now + timedelta(seconds=delay)).strftime("%a %H:%M")
```

1. **Ask the clock.** `now = clock.now()` — one call, and every branch below measures against it.
   `reset_at` is a unix epoch, so it is compared against `now.timestamp()`.
2. **Structured `reset_at` takes priority.** When `exc.reset_at` is set (the CLI's own
   `rate_limit_event.resetsAt`, attached by [`classify_turn`](classify-turn.md#ladder-first-match-wins)),
   compute `secs = exc.reset_at - now.timestamp()`:
   - **Still in the future (`secs > 0`).** The delay is `min(secs, resilience.cap_max_wait_s)` —
     bounded so a bogus far-future epoch (clock skew, a malformed event) can't stall the run for
     longer than that ceiling (env `AGENT_CAP_MAX_WAIT_S`, default `8 * 24 * 3600` = 8 days) —
     plus `resilience.cap_wait_margin_s` (env `AGENT_CAP_WAIT_MARGIN_S`, default `120`)
     so the retry lands safely *after* the window reopens rather than racing it. The `when` label
     is computed from `now + delay` — the injected clock's now, never the real one — formatted
     `"%a %H:%M"` (e.g. `"Tue 14:05"`).
   - **Already in the past (`secs <= 0`).** A stale event or clock skew — reset already happened,
     so there's nothing to wait out. Returns just the margin (`cap_wait_margin_s`) as the delay,
     with a fixed label `"reset already passed — retrying shortly"` (no timestamp computed).
3. **No structured `reset_at` → parse the message text.**
   [`parse_reset_seconds(str(exc), now)`](parse-reset-seconds.md#algorithm) looks for a reset
   clock-time embedded in the error string (e.g. `"resets 3:50am"`), measured against the same
   `now` this function was handed.
   - **Found.** `delay = parsed + resilience.cap_wait_margin_s`; the label is computed from that
     same `now` plus `delay`, formatted the same `"%a %H:%M"`.
   - **Not found.** Neither a structured epoch nor a parseable reset time — falls back to
     `resilience.cap_default_wait_s` (env `AGENT_CAP_DEFAULT_WAIT_S`, default `3600` = 1 hour) with
     a fixed label `"unknown reset — using default wait"`.

Two of the four branches (structured-past, text-not-found) return a **fixed** label string instead
of a computed timestamp — the label always states either a concrete "resuming around" time or an
explicit reason none could be computed, never a bare number.

## Related pieces

- [`AgentRunner.turn`](agent-turn.md#algorithm) — the sole caller; invokes this once per cap hit
  (`is_cap_hit`), then passes the returned `delay` to
  [`sleep_with_notice`](sleep-with-notice.md) (which does the actual sleeping and periodic "still
  paused" logging) and discards the `when` label after logging it — `turn` then
  `continue`s the same retry loop with the same session and prompt.
- [`BackendInvocationError.reset_at`](classify-turn.md#backendinvocationerror) — the structured
  signal this function prefers, set by [`classify_turn`](classify-turn.md#ladder-first-match-wins)
  from the CLI's `rate_limit_event.resetsAt` (via [`rate_limit_info`](classify-turn.md#rate_limit_info)).
- [`parse_reset_seconds`](parse-reset-seconds.md#algorithm) — the text-parsing fallback this
  function calls when `exc.reset_at` is unset.
- `Clock` (`_vendor/stablemate_core/clock.py`) — the `now`/`sleep` protocol; `SYSTEM_CLOCK` in production, a
  `FakeClock` in the cap tests.
- [GUARDRAILS.md](../../../../workhorse/docs/GUARDRAILS.md) — documents the three env vars behind
  the `resilience` fields this function reads (`AGENT_CAP_MAX_WAIT_S`, `AGENT_CAP_WAIT_MARGIN_S`,
  `AGENT_CAP_DEFAULT_WAIT_S`) from an operator's perspective.
