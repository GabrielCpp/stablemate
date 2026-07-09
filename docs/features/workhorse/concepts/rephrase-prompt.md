---
type: concept
slug: rephrase-prompt
title: _rephrase_prompt — fresh-session reframe strategies
---
# _rephrase_prompt — fresh-session reframe strategies

Builds the prompt for [`run_agent`](run-agent.md#the-ladder)'s **Layer 3 (reframe)** retry: when a
node's turn has failed and reframing is invoked, this picks one of three successively simpler
rewordings of the original prompt, keyed by how many reframes have already been tried for this
node. Distinct from [`_retry_prompt`](retry-prompt.md) (a same-session nudge after an unparseable reply)
and [`_timeout_retry_prompt`](timeout-retry-prompt.md) (a budget warning prepended after a
wall-clock kill) — this is the only one of the three that runs on a **fresh session**, so it
re-states the whole task rather than assuming any prior turn is still in context.

- code: `workhorse/workhorse/runner/agent.py::_rephrase_prompt`

## Contract

- **Input:**
  - `original_prompt: str` — the node's fully-rendered prompt (the same text on every attempt —
    reframing always restarts from this, never from a previously-reframed variant).
  - `node: AgentNode` — supplies `node.outputs` to build the output-keys contract each strategy
    states.
  - `attempt: int` — the 1-based reframe count for this node (`run_agent`'s `rephrase` counter
    *after* incrementing); selects which strategy to apply.
- **Output:** `str` — the reworded prompt to send on a **fresh session** (the caller drops
  `session_id_path` before invoking it — see [Sessions](run-agent.md#sessions)).
- **Raises:** nothing — pure string construction.

## Algorithm

```
output_keys = [o.key for o in node.outputs]
strategies = [strategy_1, strategy_2, strategy_3]     # ordered, most- to least-faithful
idx = min(attempt - 1, len(strategies) - 1)            # attempt 4+ repeats strategy 3
return strategies[idx](original_prompt)
```

Three fixed strategies, each strictly more aggressive at trading task fidelity for a parseable
reply:

1. **Attempt 1 — add structure.** Keeps the *entire* original prompt verbatim, wrapped with an
   explicit instruction and the output-keys contract: `"Please complete the following task
   carefully:\n\n{original}\n\nIMPORTANT: reply with ONLY a JSON object containing these keys:
   {output_keys}."`
2. **Attempt 2 — truncate and show the shape.** Keeps only the first 1000 characters of the
   original prompt and replaces the ask with a JSON skeleton to fill in, one `"key": <value>,`
   line per output key, fenced in a ` ```json ` block.
3. **Attempt 3+ — minimal emergency form.** Keeps only the first 500 characters, tells the model
   "reasonable values" are acceptable if unsure, and restates the bare output-keys requirement.
   `attempt > 3` reuses this same strategy (`idx` clamps at the last index) — there is no further
   fallback beyond it; `run_agent`'s own `max_rephrase_attempts` bound is what eventually stops the
   ladder, not this function running out of strategies.

Each strategy is independent — none composes with another; a later attempt does not build on the
previous attempt's wording, only on the fixed `original_prompt`.

## Related pieces

- [`run_agent`](run-agent.md#the-ladder) — the only caller; invokes this once per reframe
  (Layer 3), always after dropping the session so the reworded prompt opens a clean conversation.
- [`_retry_prompt`](retry-prompt.md) / [`_timeout_retry_prompt`](timeout-retry-prompt.md) — the
  other two prompt-mutation strategies, used in different failure paths (same-session output-parse
  retry, and a wall-clock-timeout retry respectively).
