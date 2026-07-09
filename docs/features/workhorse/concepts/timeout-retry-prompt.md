---
type: concept
slug: timeout-retry-prompt
title: _timeout_retry_prompt — budget-overrun warning
---
# _timeout_retry_prompt — budget-overrun warning

Builds the retry prompt [`_invoke_claude`](invoke-claude.md#algorithm) sends after a turn was
killed for exceeding its per-node wall-clock [`timeout`](run-agent.md#setup-once-before-the-ladder):
prepends a fixed warning that states the same budget in minutes and seconds and tells the retry to
size its work to fit, then appends the **original, unmodified** prompt. Distinct from
[`_rephrase_prompt`](rephrase-prompt.md) (a fresh-session, whole-task reframe used by `run_agent`'s
Layer 3) and [`_retry_prompt`](retry-prompt.md) (a same-session parse-error nudge) — this is the
only one of the three that fires from *inside* [`_invoke_claude`](invoke-claude.md) (Layer 1, before
a `BackendInvocationError` ever reaches `run_agent`'s ladder) and the only one that keeps the task
text completely unchanged, only prepending context.

- code: `workhorse/workhorse/runner/agent.py::_timeout_retry_prompt`
- verify: `workhorse/tests/test_agent_cap.py::test_budget_timeout_warns_retry_with_time_budget`

## Contract

- **Input:**
  - `original_prompt: str` — the exact prompt text the killed attempt was sent (`_invoke_claude`
    passes its own `prompt` parameter, never a previously-warned `attempt_prompt`, so the warning
    never stacks across repeated timeouts).
  - `timeout: float` — the per-turn wall-clock budget in seconds (`_invoke_claude`'s own `timeout`),
    the same value `backend.run_turn` was given and will be given again on the retry.
- **Output:** `str` — the warning notice concatenated with `original_prompt`, unmodified, appended
  after it.
- **Raises:** nothing — pure string construction.

## Algorithm

```
minutes = max(1, round(timeout / 60))
notice = (
    "⚠️ TIME BUDGET — your previous attempt at this task was STOPPED for exceeding its "
    f"wall-clock budget of ~{minutes} min ({int(timeout)}s), and all of its work was lost. "
    f"You get the SAME ~{minutes} min for this attempt. Do NOT run any command that cannot "
    "finish well within that budget: time long operations first, run measurements at a "
    "reduced scale if the full run will not fit, and leave margin to write your final result "
    "before time runs out. Then carry out the task below.\n\n"
)
return notice + original_prompt
```

1. **Round the budget to whole minutes**, floored at `1` so a very short `timeout` (e.g. a few
   seconds, common in tests) never reports "0 min".
2. **State the budget twice** in the fixed notice text — once in minutes (human-scannable) and once
   in raw seconds (`int(timeout)`, exact) — so the retry can't misread the unit.
3. **Instruct the retry to budget its own work**: run long operations first (so a cutoff still
   leaves the timing data), scale measurements down if the full run won't fit, and leave margin to
   emit the final JSON result before the clock runs out.
4. **Prepend, never rewrite.** The original task text follows the notice verbatim — unlike
   [`_rephrase_prompt`](rephrase-prompt.md)'s strategies, nothing about the task itself is
   shortened or restructured; only the context prepended to it changes.

## Related pieces

- [`_invoke_claude`](invoke-claude.md#algorithm) — the only caller; invokes this once per Layer-1
  retry, but only when the failed attempt's `BackendInvocationError` carries `timed_out=True` and is
  not a scheduled-reset cap (`is_cap_hit`) — a cap can also set `timed_out=True` when the CLI hangs,
  but the model never ran in that case, so no budget was actually spent.
- [`_rephrase_prompt`](rephrase-prompt.md) / [`_retry_prompt`](retry-prompt.md) — the other two
  prompt-mutation strategies, used in different failure paths (fresh-session reframe on
  `run_agent`'s Layer 3, and a same-session output-parse nudge inside
  [`_invoke_and_parse`](invoke-and-parse.md) respectively).
- [`run_agent`](run-agent.md#the-ladder) — never calls this directly; only sees its effect if the
  retried attempt still fails and the resulting `BackendInvocationError` propagates up to the
  ladder's compact/reframe layers.
