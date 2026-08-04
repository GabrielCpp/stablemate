---
type: concept
slug: rephrase-prompt
title: rephrase_prompt — fresh-session reframe strategies
---
# rephrase_prompt — fresh-session reframe strategies

Builds the prompt for [the ladder's](run-agent.md#the-ladder) **reframe layer**: when a node's turn
has failed and reframing is invoked, this picks one of three successively simpler rewordings of the
original prompt, keyed by how many reframes have already been tried for this node. Distinct from
[`retry_prompt`](retry-prompt.md) (a same-session nudge after an unparseable reply) and
[`timeout_retry_prompt`](timeout-retry-prompt.md) (a budget warning prepended after a wall-clock
kill) — this is the only one of the three that runs on a **fresh session**, so it re-states the
whole task rather than assuming any prior turn is still in context.

- code: `workhorse/workhorse/runner/reframe.py::rephrase_prompt`
- verify: `workhorse/tests/test_agent_recovery.py::test_unparseable_output_reframes_then_defaults`

## Contract

Public, and pure: it knows nothing about the runner, the backend or the session — the caller is
what drops `session_id_path` before sending what this returns.

- **Input:**
  - `original_prompt: str` — the node's fully-rendered prompt (the same text on every attempt —
    reframing always restarts from this, never from a previously-reframed variant).
  - `node: AgentNode` — supplies `node.outputs` to build the output-keys contract each strategy
    states.
  - `attempt: int` — the 1-based reframe count for this node (the ladder's `rephrase` counter
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
   fallback beyond it; `resilience.max_rephrase_attempts` (default `3`) is what eventually stops
   the ladder, not this function running out of strategies.

Each strategy is independent — none composes with another; a later attempt does not build on the
previous attempt's wording, only on the fixed `original_prompt`.

## Related pieces

- [`AgentRunner.run`](run-agent.md#the-ladder) — the only caller; invokes this once per reframe,
  always after dropping the session so the reworded prompt opens a clean conversation, and stops
  after `self.resilience.max_rephrase_attempts` of them.
- [`retry_prompt`](retry-prompt.md) / [`timeout_retry_prompt`](timeout-retry-prompt.md) — the
  other two prompt-mutation strategies in `runner/reframe.py`, used in different failure paths
  (same-session output-parse retry, and a wall-clock-timeout retry respectively).
- There is no rung below this one: once every reframe has failed the ladder re-raises and the
  run stops at its checkpoint, rather than emitting an answer the agent never gave.
