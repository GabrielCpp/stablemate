---
type: concept
slug: parse-reset-seconds
title: _parse_reset_seconds — reset-clock-time text parser
---
# _parse_reset_seconds — reset-clock-time text parser

Finds a cap-reset clock time embedded in a CLI error message's text (e.g. `"resets 3:50am"`,
`"resets at 11pm"`, `"resets 15:50"`) and converts it into a duration — seconds from `now` until
that clock time next occurs. This is the fallback [`_cap_delay_seconds`](cap-delay-seconds.md#algorithm)
calls when the caught `BackendInvocationError` carries no structured `reset_at` epoch; it never
raises, returning `None` when no reset time is found so the caller can fall back to its own fixed
default wait.

- code: `workhorse/workhorse/runner/agent.py::_parse_reset_seconds`
- verify: `workhorse/tests/test_agent_cap.py::test_parse_reset_seconds_variants`,
  `workhorse/tests/test_guardrails.py::test_reset_time_parsing`

## Contract

- **Input:**
  - `text: str` — the message to search (typically `str(exc)` from a caught
    `BackendInvocationError`).
  - `now: datetime | None` (default `None`) — the current time to measure against; `None` resolves
    to `datetime.now()`. Exposed as a parameter (rather than calling `datetime.now()` inline) so
    tests can pin "now" without patching the `datetime` module.
- **Output:** `float | None` — seconds from `now` until the next future occurrence of the parsed
  clock time, or `None` when no reset time could be found in `text`.
- **Raises:** nothing — a parse miss or an out-of-range time returns `None` rather than raising.

## Algorithm

```
now = now or datetime.now()
m = search 12-hour pattern: r"resets?(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)"  (case-insensitive)
if m:
    hour = int(group1) % 12
    if group3.lower() == "pm": hour += 12
    minute = int(group2 or 0)
else:
    m = search 24-hour pattern: r"resets?(?:\s+at)?\s+(\d{1,2}):(\d{2})\b"  (case-insensitive)
    if not m: return None
    hour, minute = int(group1), int(group2)
if not (0 <= hour <= 23 and 0 <= minute <= 59): return None
target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
if target <= now: target += timedelta(days=1)
return (target - now).total_seconds()
```

1. **Resolve "now".** The `now` parameter wins when supplied (tests pin it); otherwise
   `datetime.now()`.
2. **Try the 12-hour form first.** `resets?(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)` matches
   `"resets 3:50am"`, `"resets at 11pm"`, or a bare hour like `"resets 11pm"` (minutes optional,
   default `0`). The optional `"reset*s*"` (singular or plural) and optional `"at"` tolerate both
   phrasings the CLI emits. When it matches:
   - `hour = int(group1) % 12` folds a 12-hour clock hour (`1`–`12`) down to `0`–`11` (so `12am` →
     `0`, `12pm` → `12` after the next step).
   - `+= 12` when the am/pm group is `"pm"`, producing a 24-hour `hour` in `0`–`23`.
   - `minute = int(group2 or 0)` — the captured minute group, or `0` when omitted.
3. **Fall back to the bare 24-hour form.** Only tried when step 2's pattern didn't match:
   `resets?(?:\s+at)?\s+(\d{1,2}):(\d{2})\b` matches `"resets 15:50"` (requires the colon+minutes —
   there is no bare-hour 24-hour form). No match in either pattern → **return `None`** (the caller
   falls back to its own fixed default).
4. **Sanity-check the parsed time.** `0 <= hour <= 23 and 0 <= minute <= 59` — guards against a
   nonsensical capture (the regex's `\d{1,2}`/`\d{2}` groups accept up to `99`, e.g. `"resets
   99:99"`). Out of range → **return `None`**.
5. **Compute the next future occurrence.** `target = now` with `hour`/`minute` substituted and
   seconds/microseconds zeroed. If `target <= now` (the clock time already passed today, or is
   exactly now), roll forward one day (`target += timedelta(days=1)`) — the function always
   describes a time strictly in the future (or the present instant, before rolling).
6. **Return the gap** as `(target - now).total_seconds()`, a `float`.

## Related pieces

- [`_cap_delay_seconds`](cap-delay-seconds.md#algorithm) — the sole caller; calls this only when
  `exc.reset_at` is unset, and on a non-`None` result adds its own fixed
  `_CAP_WAIT_MARGIN_S` margin before returning the delay to
  [`_invoke_claude`](invoke-claude.md#algorithm).
- [`BackendInvocationError`](classify-turn.md#backendinvocationerror) — `str(exc)` is the `text`
  this function searches; its structured `reset_at` field (when present) bypasses this parser
  entirely.

