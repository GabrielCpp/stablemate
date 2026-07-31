---
type: concept
slug: invoke-and-parse
title: AgentRunner._invoke_and_parse — same-session output-retry loop
---
# AgentRunner._invoke_and_parse — same-session output-retry loop

The layer [`AgentRunner.run`](run-agent.md#the-ladder) calls once per ladder attempt: runs one
agent-CLI turn via [`turn`](agent-turn.md) and parses its text into the node's declared outputs
([`extract_outputs`](extract-outputs.md)). When the text can't be parsed, it re-prompts **within the
same session** — distinct from `run`'s own reframe layer, which drops the session and starts fresh.
This is the boundary where an `OutputParseError` is either absorbed (retried in-session) or allowed
to escape to the ladder.

- code: `workhorse/workhorse/runner/ladder.py::AgentRunner._invoke_and_parse`
- verify: `workhorse/tests/test_agent_recovery.py::test_unparseable_output_reframes_then_defaults`

## Contract

A private method on the [`AgentRunner`](run-agent.md#the-runner) dataclass. The retry budget is
**not** a parameter — it is read from `self.resilience.max_output_retries` — and neither is the
backend or the clock, which reach the CLI through `turn`.

- **Input:**
  - `prompt: str` — the prompt for the first attempt (the rendered node prompt, or a reframed
    variant chosen by the caller).
  - `node: AgentNode` — supplies `node.id` (logging) and `node.outputs` (the keys
    `extract_outputs` must find).
  - `session_id_path: Path | None` — passed straight through to `turn`; unchanged across
    retries, so every attempt in this loop resumes the **same** session.
  - `model: str | None` — passed straight through to `turn`.
  - `timeout: float` (keyword-only) — the per-turn wall-clock budget, resolved once by the caller.
  - `cwd: str | None`, `add_dirs: list[str] | None`, `effort: str | None` (keyword-only) — passed
    straight through to `turn`.
- **From `self`:** `resilience.max_output_retries` (default `2`, env `AGENT_MAX_OUTPUT_RETRIES`) —
  additional same-session attempts after the first; total attempts = `max_output_retries + 1`.
- **Output:** `dict[str, Any]` — the node's extracted outputs, as returned by `extract_outputs`.
- **Raises:**
  - `OutputParseError` — re-raised once `attempt >= max_output_retries` and parsing still fails;
    the caller catches this in [the ladder](run-agent.md#the-ladder) as a signal to
    reframe (or, on a `BackendInvocationError` with `overflow=True` from `turn` instead,
    to try compaction first).
  - `BackendInvocationError` — propagated unchanged from `turn` (this method adds no
    handling for it; a failed turn aborts the loop immediately).

## Algorithm

```
max_output_retries = self.resilience.max_output_retries
for attempt in 0 .. max_output_retries:
    result_text = self.turn(prompt, node.id, session_id_path, model=model, timeout=timeout,
                            cwd=cwd, add_dirs=add_dirs, effort=effort)
    try:
        return extract_outputs(result_text, node)
    except OutputParseError as exc:
        if attempt >= max_output_retries:
            raise
        print("⚠ output parse failed (attempt N/M): exc; retrying")
        prompt = retry_prompt(node, exc)   # next iteration reuses session_id_path unchanged
```

1. **Invoke.** [`turn`](agent-turn.md) runs one turn and returns its raw result text, or raises
   `BackendInvocationError` (propagated immediately — this loop only retries *parse* failures, not
   invocation failures; the transient and cap recoveries already happened one layer down).
2. **Parse.** `extract_outputs(result_text, node)` turns the text into the node's declared
   outputs dict; success returns immediately.
3. **On `OutputParseError`, decide whether to retry in-session.** If this was the last allowed
   attempt (`attempt >= max_output_retries`), re-raise so the caller escalates. Otherwise log a
   warning and continue: `session_id_path` is untouched (the CLI turn that just ran already
   persisted it), so the next `turn` call **resumes** that same session rather than
   starting over.
4. **Build the corrective prompt.** [`retry_prompt(node, exc)`](retry-prompt.md) replaces `prompt`
   with a short nudge — "reply with ONLY a JSON object containing exactly these keys: […]" —
   naming `node.outputs`' keys and the parse error, explicitly asking the agent not to redo any
   work (the session already has the prior turn's output attempt in context).
5. Loop back to step 1 with the new `prompt` and the unchanged `session_id_path`.

The `for` loop always either `return`s from step 2 or `raise`s from step 3 on its final iteration;
the trailing `raise AssertionError(...)` after the loop is unreachable and exists only to satisfy
the type checker that the method always returns or raises.

## Related pieces

- [`AgentRunner.turn`](agent-turn.md) — runs one CLI turn, including its own transient-retry and
  cap-wait handling (a lower resilience layer than this one).
- [`extract_outputs`](extract-outputs.md) / `parse_json_from_text` (`runner/extract.py`) — parse a
  turn's raw text into the declared outputs, raising `OutputParseError` on failure.
- [`retry_prompt`](retry-prompt.md) (`runner/reframe.py`) — builds the corrective same-session
  nudge.
- [`AgentRunner.run`](run-agent.md) — the caller; owns the four-layer ladder (transient → compact →
  reframe → default) that this method's `BackendInvocationError`/`OutputParseError` feed into.
