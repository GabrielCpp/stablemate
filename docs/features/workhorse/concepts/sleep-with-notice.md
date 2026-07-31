---
type: concept
slug: sleep-with-notice
title: sleep_with_notice — periodically-announced cap-wait sleep
---
# sleep_with_notice — periodically-announced cap-wait sleep

Performs the actual sleeping for a cap wait: [`AgentRunner.turn`](agent-turn.md#algorithm) calls
this once per cap hit, passing the `delay` [`cap_delay_seconds`](cap-delay-seconds.md) computed.
Rather than a single blocking sleep of `total_s`, it sleeps in fixed-size chunks and, after each
chunk, emits a cap-wait heartbeat metric and prints a "still paused" line — so both an operator
watching the log and a collector watching the telemetry can tell a long, legitimate cap wait
(hours, sometimes days) from an actual hang.

- code: `workhorse/workhorse/runner/caps.py::sleep_with_notice`
- verify: `workhorse/tests/test_agent_cap.py::test_cap_sleeps_until_reset_then_resumes`

## Contract

Public, and it neither sleeps nor times anything itself — the sleeping goes through the injected
clock, which is why a test can watch an eight-hour cap wait elapse instantly.

- **Input:**
  - `total_s: float` — total seconds to sleep, as computed by
    [`cap_delay_seconds`](cap-delay-seconds.md).
  - `node_id: str` — the workflow node this wait belongs to; included in each "still paused" line
    and used as the heartbeat's node label.
  - `label: str` — a short reason string included in each "still paused" line (`turn` passes
    `"cap reset"`).
  - `resilience: AgentResilience` (keyword-only) — read for `cap_tick_s`, the chunk size. This was
    a module constant read from the environment at import time; it is a field on the run's
    resilience policy now.
  - `clock: Clock` (keyword-only) — every sleep goes through `clock.sleep(chunk)`; nothing here
    calls `time.sleep`.
- **Output:** `None`.
- **Raises:** nothing.

## Algorithm

```
remaining = total_s
otel.heartbeat(node_id, remaining)
while remaining > 0:
    chunk = min(remaining, resilience.cap_tick_s)
    clock.sleep(chunk)
    remaining -= chunk
    otel.heartbeat(node_id, remaining)
    if remaining > 0:
        print(f"[{node_id}] ⏸ still paused ({label}); ~{int(remaining)}s remaining")
```

1. **Heartbeat before sleeping at all.** `otel.heartbeat(node_id, remaining)` fires once with the
   full `total_s`, so a collector learns the run is entering a cap wait — and how long it expects
   to be there — before the first silent chunk rather than a tick later.
2. **Chunk the wait.** Sleeps in increments of at most `resilience.cap_tick_s` (env
   `AGENT_CAP_TICK_S`, default `600` = 10 minutes) rather than one call covering the full
   `total_s`, so the loop can report progress between chunks.
3. **Heartbeat after every chunk, including the last.** The metric is the external liveness proof;
   the final one carries `remaining == 0` and marks the wait's end.
4. **Print after every chunk but the last.** If time still remains (`remaining > 0`), prints
   `"[{node_id}] ⏸ still paused ({label}); ~{int(remaining)}s remaining"` — no line is printed once
   the final chunk completes, so the wait ends silently on the console and the caller's own
   "resuming" line (`turn`'s `"▶ cap wait elapsed — resuming node"`) is the last word on it.

## Related pieces

- [`AgentRunner.turn`](agent-turn.md#algorithm) — the sole caller; sleeps here on every cap hit
  (`is_cap_hit`), then prints its own "resuming" line and `continue`s the retry loop with the same
  session and prompt.
- [`cap_delay_seconds`](cap-delay-seconds.md) — computes the `total_s` this function sleeps and the
  "resuming around" label `turn` prints alongside this function's periodic ticks.
- `Clock` (`runner/clock.py`) — the `now`/`sleep` protocol; `SYSTEM_CLOCK` in production, a
  `FakeClock` in the cap tests, which is what makes a multi-day wait testable.
- [GUARDRAILS.md](../../../../workhorse/docs/GUARDRAILS.md) — documents `AGENT_CAP_TICK_S` from an
  operator's perspective.
