---
type: concept
slug: retry-prompt
title: _retry_prompt — same-session output-parse nudge
---
# _retry_prompt — same-session output-parse nudge

Builds the corrective follow-up prompt [`_invoke_and_parse`](invoke-and-parse.md#algorithm) sends
when a turn's text failed `_extract_outputs`: a short, same-session nudge that names the exact
output keys still required and the parse error that just occurred, and tells Claude not to redo any
work. Distinct from [`_rephrase_prompt`](rephrase-prompt.md) (a **fresh-session**, whole-task
reframe used by `run_agent`'s Layer 3 ladder) and [`_timeout_retry_prompt`](timeout-retry-prompt.md)
(a budget warning prepended after a wall-clock kill) — this is the only one of the three that
assumes the prior turn is still live in context, since the caller never drops `session_id_path`
around it.

- code: `workhorse/workhorse/runner/agent.py::_retry_prompt`

## Contract

- **Input:**
  - `node: AgentNode` — supplies `node.outputs` (a list of `OutputSpec`); only each entry's `key` is
    used, to name the JSON keys the reply must contain.
  - `error: OutputParseError` — the exception `_extract_outputs` raised on this attempt; its `str()`
    is embedded verbatim in the corrective prompt so Claude sees what went wrong.
- **Output:** `str` — the replacement prompt for the next same-session attempt.
- **Raises:** nothing — pure string construction.

## Algorithm

```
keys = [o.key for o in node.outputs]
return (
    "Your previous response could not be parsed into this node's required outputs.\n"
    f"Error: {error}\n\n"
    "Do not redo any work. Reply with ONLY a single JSON object "
    "(optionally inside a ```json fenced code block) containing exactly "
    f"these keys: {keys}. Include no other commentary before or after it."
)
```

One fixed template, no branching: state the parse failure, forbid re-doing the task's work (the
session already holds the prior turn's attempt), and restate the exact output-key contract the
reply must satisfy. Unlike [`_rephrase_prompt`](rephrase-prompt.md)'s three escalating strategies,
there is only ever this one wording — the caller's loop (`_invoke_and_parse`) is what bounds how
many times it gets sent (`max_output_retries`), not this function.

## Related pieces

- [`_invoke_and_parse`](invoke-and-parse.md#algorithm) — the only caller; invokes this once per
  failed parse attempt, on the last iteration of its retry loop before giving up and re-raising
  `OutputParseError` to `run_agent`.
- [`_rephrase_prompt`](rephrase-prompt.md) / [`_timeout_retry_prompt`](timeout-retry-prompt.md) —
  the other two prompt-mutation strategies, used in different failure paths (fresh-session reframe,
  and a wall-clock-timeout retry respectively).
- [`OutputParseError`](extract-outputs.md) — the exception type this function's `error` parameter
  accepts; raised by `_extract_outputs` and defined alongside it in `runner/agent.py`.
