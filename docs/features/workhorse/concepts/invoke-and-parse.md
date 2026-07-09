---
type: concept
slug: invoke-and-parse
title: _invoke_and_parse — same-session output-retry loop
---
# _invoke_and_parse — same-session output-retry loop

The layer [run_agent](run-agent.md#the-ladder) calls once per ladder attempt: runs one agent-CLI
turn via `_invoke_claude` and parses its text into the node's declared `outputs`
(`_extract_outputs`). When the text can't be parsed, it re-prompts **within the same session** —
distinct from `run_agent`'s own reframe layer, which drops the session and starts fresh. This is
the boundary where an `OutputParseError` is either absorbed (retried in-session) or allowed to
escape to `run_agent`'s ladder.

- code: `workhorse/workhorse/runner/agent.py::_invoke_and_parse`

## Contract

- **Input:**
  - `prompt: str` — the prompt for the first attempt (the rendered node prompt, or a reframed
    variant chosen by the caller).
  - `node: AgentNode` — supplies `node.id` (logging) and `node.outputs` (the keys
    `_extract_outputs` must find).
  - `session_id_path: Path | None` — passed straight through to `_invoke_claude`; unchanged across
    retries, so every attempt in this loop resumes the **same** session.
  - `model: str | None`, `effort: str | None` — passed straight through to `_invoke_claude`.
  - `max_output_retries: int` — additional same-session attempts after the first; total attempts
    = `max_output_retries + 1`.
  - `timeout: float` (default `DEFAULT_RESULT_TIMEOUT_S`), `cwd: str | None`,
    `add_dirs: list[str] | None` — passed straight through to `_invoke_claude`.
- **Output:** `dict[str, Any]` — the node's extracted outputs, as returned by `_extract_outputs`.
- **Raises:**
  - `OutputParseError` — re-raised once `attempt >= max_output_retries` and parsing still fails;
    the caller (`run_agent`) catches this in [the ladder](run-agent.md#the-ladder) as a signal to
    reframe (or, on a `BackendInvocationError` with `overflow=True` from `_invoke_claude` instead,
    to try compaction first).
  - `BackendInvocationError` — propagated unchanged from `_invoke_claude` (this function adds no
    handling for it; a failed turn aborts the loop immediately).

## Algorithm

```
for attempt in 0 .. max_output_retries:
    result_text = _invoke_claude(prompt, node.id, session_id_path, model, timeout,
                                  cwd, add_dirs, effort)
    try:
        return _extract_outputs(result_text, node)
    except OutputParseError as exc:
        if attempt >= max_output_retries:
            raise
        print("⚠ output parse failed (attempt N/M): exc; retrying")
        prompt = _retry_prompt(node, exc)   # next loop iteration reuses session_id_path unchanged
```

1. **Invoke.** `_invoke_claude` runs one turn and returns its raw result text, or raises
   `BackendInvocationError` (propagated immediately — this loop only retries *parse* failures, not
   invocation failures).
2. **Parse.** `_extract_outputs(result_text, node)` turns the text into the node's declared
   `outputs` dict; success returns immediately.
3. **On `OutputParseError`, decide whether to retry in-session.** If this was the last allowed
   attempt (`attempt >= max_output_retries`), re-raise so the caller escalates. Otherwise log a
   warning and continue: `session_id_path` is untouched (the CLI turn that just ran already
   persisted it), so the next `_invoke_claude` call **resumes** that same session rather than
   starting over.
4. **Build the corrective prompt.** [`_retry_prompt(node, exc)`](retry-prompt.md) replaces `prompt`
   with a short nudge — "reply with ONLY a JSON object containing exactly these keys: […]" —
   naming `node.outputs`' keys and the parse error, explicitly asking Claude not to redo any work
   (the session already has the prior turn's output attempt in context).
5. Loop back to step 1 with the new `prompt` and the unchanged `session_id_path`.

The `for` loop always either `return`s from step 2 or `raise`s from step 3 on its final iteration;
the trailing `raise AssertionError(...)` after the loop is unreachable and exists only to satisfy
the type checker that the function always returns or raises.

## Related pieces

- [`_invoke_claude`](invoke-claude.md) — runs one CLI turn, including its own transient-retry and
  cap-wait handling (a lower resilience layer than this one).
- [`_extract_outputs`](extract-outputs.md) / `_parse_json_from_text` — parse a turn's raw text into
  the declared outputs, raising `OutputParseError` on failure.
- [`_retry_prompt`](retry-prompt.md) — builds the corrective same-session nudge.
- [`run_agent`](run-agent.md) — the caller; owns the four-layer ladder (transient → compact →
  reframe → default) that this function's `BackendInvocationError`/`OutputParseError` feed into.
  `max_output_retries` is `run_agent`'s `max_output_retries` parameter, forwarded unchanged.
