---
type: concept
slug: agent-turn
title: AgentRunner.turn — the transient-retry/cap-wait invocation layer
---
# AgentRunner.turn — the transient-retry/cap-wait invocation layer

Layer 1 of [the ladder](run-agent.md#the-ladder): runs **one** agent-CLI turn through the injected
[`AgentBackend`](agent-backend.md) and returns its raw result text, absorbing the failures that
clear on their own. Two recovery modes, deliberately different in kind — a *scheduled* spending or
usage cap is **waited out** (the run sleeps until the window reopens, however long that is), while
a *short* transient (rate limit, overload, network blip, budget timeout) gets **bounded exponential
backoff** and then fails fast up to the ladder.

> **This page was `invoke-claude.md`.** The unit names no CLI any more, and no longer resolves one:
> `AGENT_CLI` is read once at the CLI boundary and the chosen adapter is handed to the runner, so
> this method drives `self.backend.run_turn` and knows nothing else about what is behind it. The
> old filename said otherwise, so it was renamed rather than kept for link stability.

- code: `workhorse/workhorse/runner/ladder.py::AgentRunner.turn`

The resilience contract is covered by `workhorse/tests/test_agent_cap.py::test_cap_sleeps_until_reset_then_resumes`,
`workhorse/tests/test_agent_cap.py::test_cap_waits_do_not_consume_short_retry_budget`,
`workhorse/tests/test_agent_cap.py::test_cap_wait_safety_bound`,
`workhorse/tests/test_agent_cap.py::test_short_transient_uses_bounded_backoff_then_fails`,
`workhorse/tests/test_agent_cap.py::test_non_transient_fails_immediately`,
`workhorse/tests/test_agent_cap.py::test_budget_timeout_warns_retry_with_time_budget`,
`workhorse/tests/test_agent_cap.py::test_non_timeout_transient_retries_prompt_unchanged`, and
`workhorse/tests/test_agent_cap.py::test_structured_reset_at_drives_invoke_wait`.

The same transient-retry layer's reload and budget behavior is exercised by
`workhorse/tests/test_agent_recovery.py::test_a_reload_is_neither_retried_nor_reframed`,
`workhorse/tests/test_agent_recovery.py::test_the_cut_turn_closes_its_span_and_closes_it_cleanly`,
`workhorse/tests/test_agent_recovery.py::test_transient_failure_still_reframes_not_aborts`,
`workhorse/tests/test_agent_recovery.py::test_node_invoke_retries_bounds_transient_retries_below_the_run_default`,
`workhorse/tests/test_agent_recovery.py::test_node_invoke_retries_unset_keeps_the_run_default`, and
`workhorse/tests/test_agent_recovery.py::test_a_day_long_outage_is_slept_through_not_failed_through`.

## Contract

A method on the [`AgentRunner`](run-agent.md#the-runner) dataclass, so the backend, the resilience
knobs and the clock come from `self` — they are not parameters, and there is no fallback path that
resolves any of them.

- **Input:**
  - `prompt: str` — the text to send.
  - `node_id: str` — used only for the console prefix and the otel events.
  - `session_id_path: Path | None` — the run's [`.session_id`](../run-artifacts.md#session_id);
    passed through to the backend, which persists the resulting id so the next call can `--resume`.
  - `model: str | None` (default `None`) — the concrete model, already resolved from the node's
    [`power:`](../workflow-format.md#power) tier by the caller.
    - `timeout: float` (keyword-only) — the per-turn wall-clock budget in seconds.
    - `prompt_path: Path | None` (keyword-only) — the already-persisted rendered prompt, passed to
      the backend for invocation diagnostics.
    - `cwd: str | None`, `add_dirs: list[str] | None`, `effort: str | None` (keyword-only) — passed
      straight through to `backend.run_turn`.
    - `invoke_retries: int | None` (keyword-only) — when set, replaces
      `resilience.max_invoke_retries` for this turn's short-transient retry budget.
    - `budget_scale: float` (keyword-only, default `1.0`) — the active power tier's
      [`timeout_scale`](../workflow-format.md#power), already folded into `timeout` by the caller.
      Carried here only so a scaled turn can be told apart from one whose `timeout` was hand-edited
      in the workflow, a distinction `timeout` alone cannot make.
    - `base_timeout_s: float | None` (keyword-only, default `None`) — the unscaled node timeout
      `timeout` was multiplied by, recorded alongside `budget_scale`.
- **From `self`:** `backend` (the injected adapter), `resilience` (`max_invoke_retries`,
  `max_cap_waits`, `invoke_backoff_base_s`, `invoke_backoff_cap_s`, and the cap knobs the helpers
  read), `clock` (every `sleep` in this method and every `now` under it).
- **Output:** `str` — the completed turn's result text, for
  [`extract_outputs`](extract-outputs.md) to parse.
- consistency: backend-invocation-error — `BackendInvocationError` propagates immediately for non-transient failures, after
  `resilience.max_invoke_retries` short retries, or after `resilience.max_cap_waits` cap waits
  (default `128`, the backstop against a cap that never actually clears).
- emits: `budget_scaled` otel event, carrying `scale` and `base_timeout_s`, when `budget_scale` is
  not `1.0` — silent on an unscaled turn, so an unscaled run says nothing about scaling at all.
- verify: emitted(event="budget_scaled", count=1)

## Algorithm

```
short_attempt = 0; cap_waits = 0; attempt_prompt = prompt
loop:
    try:
        otel.turn_start(...)
        if budget_scale != 1.0: otel.turn_event("budget_scaled", scale=budget_scale, base_timeout_s=base_timeout_s)
        result = self.backend.run_turn(attempt_prompt, node_id, session_id_path, model,
                                       prompt_path=prompt_path, timeout=timeout, resilience=self.resilience,
                                       cwd=cwd, add_dirs=add_dirs, effort=effort)
        otel.turn_end(); return result
    except BackendInvocationError as exc:
        otel.turn_end(error=str(exc))
        if not exc.transient: raise                       # straight up to the ladder
        is_cap_hit = exc.reset_at is not None or is_cap(str(exc))
        attempt_prompt = (timeout_retry_prompt(prompt, timeout)
                          if exc.timed_out and not is_cap_hit else prompt)
        if is_cap_hit:
            if cap_waits >= resilience.max_cap_waits: raise
            cap_waits += 1
            delay, when = cap_delay_seconds(exc, resilience=..., clock=self.clock)
            sleep_s = min(delay, resilience.cap_probe_s) when cap probing is enabled
            consume recovery budget; sleep_with_notice(sleep_s, node_id, "cap probe" or "cap reset",
                                                       ... reload-aware channel ...)
            re-enter on a reload cut
            continue                                       # NOT counted against short retries
        if short_attempt >= (resilience.max_invoke_retries if invoke_retries is None else invoke_retries): raise
        delay = min(resilience.invoke_backoff_base_s * 2**short_attempt,
                    resilience.invoke_backoff_cap_s)
        short_attempt += 1
        consume recovery budget; sleep_with_notice(delay, node_id, "transient failure",
                                                   ... reload-aware channel ...)
        re-enter on a reload cut
```

1. **Invoke.** One `backend.run_turn`, bracketed by an otel agent-turn span. A clean return is the
    only exit that isn't an exception. When `budget_scale` differs from `1.0`, a `budget_scaled`
    event carrying `scale` and `base_timeout_s` opens the span first, so a benchmark comparing a
    scaled tier against an unscaled one can tell "this node's timeout was multiplied by its tier"
    from "somebody edited the number in the workflow" — a distinction `timeout` alone can't make.
2. **Reload interruption → re-enter immediately.** A `ReloadRequested` raised during an invocation
   closes its otel turn span cleanly and escapes without consuming a short retry, cap wait, backoff,
   or recovery-wait budget. The partially completed turn's recorded cost and duration remain part of
   that clean span; the operator deliberately cut it rather than the turn failing.
3. **Non-transient → re-raise now.** A crashed CLI or a hard server error goes straight to
   [the ladder's non-recoverable fast path](run-agent.md#the-ladder); nothing here can help it.
4. **Classify the transient as cap or not.** `is_cap_hit` is true when the error carries a
   structured `reset_at` epoch **or** [`is_cap`](classify-turn.md#is_cap) recognises the message
   text. This one boolean decides both of the next two steps.
5. **Budget-overrun warning — only for a real overrun.** When `exc.timed_out` and it is *not* a cap
   hit, the next attempt's prompt becomes
   [`timeout_retry_prompt(prompt, timeout)`](timeout-retry-prompt.md), telling the retry it overran
   and how long it has. A cap-triggered early abort also carries `timed_out=True` (the stream loop
   breaks the same way) but must **not** get the warning — the model never ran, so no budget was
   spent. Every other transient retries the prompt unchanged.
- consistency: attempt-prompt — each budget-timeout retry derives its prompt from the original `prompt`, so the
   timeout warning appears only once rather than stacking across retries
6. **Cap → wait or probe.** [`cap_delay_seconds`](cap-delay-seconds.md) computes the scheduled
   reopening and a human label. When `resilience.cap_probe_s` is positive and shorter than that
   delay, [`sleep_with_notice`](sleep-with-notice.md) waits only one probe interval before retrying:
   an operator can clear a cap early by changing the plan, adding credit, or resetting the limit.
   Otherwise it waits to the scheduled reset. Both waits consume the active recovery-wait budget,
   print proof of life, and can be cut by a reload; a reload re-enters the ladder without spending a
   retry or cap-wait counter. Then `continue` with the same session and prompt. `cap_waits`, bounded
   by `resilience.max_cap_waits`, records each pass through this branch.
- consistency: short-attempt — a cap wait leaves `short_attempt` unchanged, so it consumes none of
   `resilience.max_invoke_retries`
7. **Short transient → bounded backoff.** `min(invoke_backoff_base_s * 2**short_attempt,
   invoke_backoff_cap_s)` (defaults `15s` doubling to a `1800s` ceiling) is consumed from the active
   recovery-wait budget and slept through [`sleep_with_notice`](sleep-with-notice.md), which can be
   cut by a reload. It retries up to `invoke_retries` when the node sets it, otherwise
   `resilience.max_invoke_retries` (default `60`), before re-raising to the ladder's compact/reframe
   layers.

Every wait in this method goes through the injected clock, which is why a test can exercise a cap
that reopens eight hours out by stating the hour rather than patching `time`.

## Related pieces

- [`AgentRunner.run`](run-agent.md) — the ladder above this layer; the `BackendInvocationError`
  that finally escapes here is what its compact/reframe/default layers act on.
- [`AgentRunner._invoke_and_parse`](invoke-and-parse.md) — the direct caller, one level up: it
  calls this once per attempt and parses the returned text.
- [`classify_turn`](classify-turn.md) (`runner/failure.py`) — where `transient`, `timed_out`,
  `overflow` and `reset_at` are set on the error this method branches on.
- [`cap_delay_seconds`](cap-delay-seconds.md) / [`sleep_with_notice`](sleep-with-notice.md)
  (`runner/caps.py`) — the cap-wait duration and the visible sleep.
- [`timeout_retry_prompt`](timeout-retry-prompt.md) (`runner/reframe.py`) — the budget warning
  prepended on a genuine overrun.
- [`AgentBackend`](agent-backend.md) — the port `self.backend` implements; `run_turn` is the only
  method this layer calls.
- [GUARDRAILS.md](../../../../workhorse/docs/GUARDRAILS.md) — the operator-facing view of the
  `AGENT_*` knobs behind every `resilience` field named above.
