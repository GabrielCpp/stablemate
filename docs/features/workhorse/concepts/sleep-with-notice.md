---
type: concept
slug: sleep-with-notice
title: _sleep_with_notice — periodically-announced cap-wait sleep
---
# _sleep_with_notice — periodically-announced cap-wait sleep

Performs the actual sleeping for a cap wait: [`_invoke_claude`](invoke-claude.md#algorithm) calls
this once per cap hit, passing the `delay` [`_cap_delay_seconds`](cap-delay-seconds.md) computed.
Rather than a single blocking `time.sleep(total_s)`, it sleeps in fixed-size chunks and prints a
"still paused" line after each chunk that doesn't finish the wait — so an operator watching the log
during a long, legitimate cap wait (hours, sometimes days) sees periodic proof of life instead of
mistaking the pause for a hang.

- code: `workhorse/workhorse/runner/agent.py::_sleep_with_notice`

## Contract

- **Input:**
  - `total_s: float` — total seconds to sleep, as computed by
    [`_cap_delay_seconds`](cap-delay-seconds.md).
  - `node_id: str` — the workflow node this wait belongs to; included in each "still paused" line.
  - `label: str` — a short reason string included in each "still paused" line (`_invoke_claude`
    passes `"cap reset"`).
- **Output:** `None`.
- **Raises:** nothing.

## Algorithm

```
remaining = total_s
while remaining > 0:
    chunk = min(remaining, _CAP_TICK_S)
    time.sleep(chunk)
    remaining -= chunk
    if remaining > 0:
        print(f"[{node_id}] ⏸ still paused ({label}); ~{int(remaining)}s remaining")
```

1. **Chunk the wait.** Sleeps in increments of at most `_CAP_TICK_S` (env `AGENT_CAP_TICK_S`,
   default `600` = 10 minutes) rather than one call covering the full `total_s`, so the loop can
   print progress between chunks.
2. **Announce after every chunk but the last.** After each `time.sleep(chunk)`, if time still
   remains (`remaining > 0`), prints `"[{node_id}] ⏸ still paused ({label}); ~{int(remaining)}s
   remaining"` — no line is printed once the final chunk completes and `remaining` reaches `0`, so
   the wait ends silently and the caller's own "resuming" line (`_invoke_claude`'s `"▶ cap wait
   elapsed — resuming node"`) is the last word on it.

## Related pieces

- [`_invoke_claude`](invoke-claude.md#algorithm) — the sole caller; sleeps here on every cap hit
  (`is_cap_hit`), then prints its own "resuming" line and `continue`s the retry loop with the same
  session and prompt.
- [`_cap_delay_seconds`](cap-delay-seconds.md) — computes the `total_s` this function sleeps and the
  "resuming around" label `_invoke_claude` prints alongside this function's periodic ticks.
- [GUARDRAILS.md](../../../../workhorse/docs/GUARDRAILS.md) — documents `AGENT_CAP_TICK_S` from an
  operator's perspective.
