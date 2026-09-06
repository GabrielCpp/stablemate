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
- tests: `workhorse/tests/test_agent_cap.py::test_cap_delay_prefers_structured_reset_at`,
  `workhorse/tests/test_agent_cap.py::test_cap_delay_falls_back_to_text_then_default`

## Contract

Public, and its two collaborators are keyword-only injections rather than module constants and a
call to `time.time()`. Nothing here reads the environment or the wall clock.

The `exc: BackendInvocationError` argument is the caught cap failure. The function reads only its
[`reset_at`](classify-turn.md#backendinvocationerror) field and its `str(exc)` message text. The
keyword-only `resilience: AgentResilience` argument supplies `cap_max_wait_s`,
`cap_wait_margin_s`, and `cap_default_wait_s`. These values were loose module constants read from
the environment at import time; they are fields on the run's resilience policy now, so a test
states a bound instead of setting an env var. The keyword-only `clock: Clock` argument supplies
"now" through `clock.now()`, a `datetime`. Both the structured and text-parsing paths read it, so
a cap that reopens eight hours out is a test that states the hour rather than one that patches
`time`.

The structured future-reset, structured stale-reset, parsed-text, and unparseable-text paths each
produce a delay and label; this helper has no separate failure result for a classified cap.

- **Output:** `tuple[float, str]` — `(delay_seconds, when_label)`: how long to sleep, and a
  label describing when the wait ends (or why it's short).

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

**Clock snapshot.** `now = clock.now()` is called once, and every branch measures against that
value. `reset_at` is a unix epoch, so the comparison uses `now.timestamp()`.

**Structured reset path.** A populated `exc.reset_at` selects this path before message parsing.
The value comes from the CLI's `rate_limit_event.resetsAt`, attached by
[`classify_turn`](classify-turn.md#ladder-first-match-wins), and the remaining interval is
`secs = exc.reset_at - now.timestamp()`.

For a future reset (`secs > 0`), the delay is `min(secs, resilience.cap_max_wait_s)`. The bound
keeps a bogus far-future epoch caused by clock skew or a malformed event from stalling the run
past that ceiling (env `AGENT_CAP_MAX_WAIT_S`, default `8 * 24 * 3600` = 8 days). Adding
`resilience.cap_wait_margin_s` (env `AGENT_CAP_WAIT_MARGIN_S`, default `120`) places the retry
after the window reopens rather than racing it. The `when` label comes from the injected clock's
`now + delay`, not the real clock, formatted as `"%a %H:%M"` (for example, `"Tue 14:05"`).

For a reset already in the past (`secs <= 0`), the event is stale or the clocks are skewed and
there is no reset interval left to wait out. The result uses only `cap_wait_margin_s` as the delay
and the fixed label `"reset already passed — retrying shortly"`, without computing a timestamp.

**Text fallback.** Without a structured `reset_at`,
[`parse_reset_seconds(str(exc), now)`](parse-reset-seconds.md#algorithm) looks for a reset
clock-time embedded in the error string (for example, `"resets 3:50am"`), measured against the
same `now` this function received.

When parsing succeeds, `delay = parsed + resilience.cap_wait_margin_s`; the label is computed
from that same `now` plus `delay` and formatted as `"%a %H:%M"`. When parsing fails, neither a
structured epoch nor a parseable reset time is available, so the result uses
`resilience.cap_default_wait_s` (env `AGENT_CAP_DEFAULT_WAIT_S`, default `3600` = 1 hour) with the
fixed label `"unknown reset — using default wait"`.

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
