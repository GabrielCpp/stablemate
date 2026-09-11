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
- tests: `workhorse/tests/test_agent_recovery.py::test_a_wrong_shaped_reply_is_corrected_in_session_not_fatal`,
  `workhorse/tests/test_agent_recovery.py::test_a_persistently_wrong_shape_stops_the_run_instead_of_passing_it_on`,
  `workhorse/tests/test_agent_recovery.py::test_unparseable_output_reframes_then_stops`,
  `workhorse/tests/test_agent_recovery.py::test_retry_wait_budget_is_shared_across_output_retries`

## Contract

A private method on the [`AgentRunner`](run-agent.md#the-runner) dataclass. The retry budget is
**not** a parameter — it is read from `self.resilience.max_output_retries` — and neither is the
backend or the clock, which reach the CLI through `turn`.

### Inputs

| Parameter | Meaning |
| --- | --- |
| `prompt: str` | The prompt for the first attempt: the rendered node prompt or a reframed variant chosen by the caller. |
| `node: AgentNode` | Supplies `node.id` for logging and `node.outputs`, whose declared keys `extract_outputs` extracts from the result text. |
| `session_id_path: Path | None` | Passes straight through to `turn` and remains unchanged across retries, so every attempt in this loop resumes the **same** session. |
| `model: str | None` | Passes straight through to `turn`. |
| `prompt_path: Path | None` (keyword-only) | Passes the already-persisted rendered-prompt path through to `turn` for backend inspection. |
| `timeout: float` (keyword-only) | The per-turn wall-clock budget, resolved once by the caller. |
| `budget_scale: float` (keyword-only, default `1.0`) | Passes straight through to `turn`, which emits a `budget_scaled` telemetry event when it differs from `1.0` — the active power tier's `timeout_scale`, so a scaled run is distinguishable from one whose `timeout` was simply edited. |
| `base_timeout_s: float | None` (keyword-only) | Passes straight through to `turn`; the pre-scale timeout, carried only for that same `budget_scaled` telemetry event. |
| `cwd: str | None`, `add_dirs: list[str] | None`, `effort: str | None` (keyword-only) | Pass straight through to `turn`. |
| `validate` (keyword-only) | An optional callback that accepts the extracted outputs and checks the caller's result shape; a validation exception becomes an `OutputParseError` and follows the same corrective retry path as malformed output. |

- **From `self`:** `resilience.max_output_retries` (default `2`, env `AGENT_MAX_OUTPUT_RETRIES`) —
  additional same-session attempts after the first; total attempts = `max_output_retries + 1`.
- **Output:** `dict[str, Any]` — the node's extracted outputs, as returned by `extract_outputs`.

After the final allowed parse attempt, the method re-raises `OutputParseError`; [the
ladder](run-agent.md#the-ladder) catches it to reframe, while a `BackendInvocationError` with
`overflow=True` instead reaches compaction first. Other `BackendInvocationError` instances pass
through unchanged from `turn`, so a failed invocation ends this parse-retry loop immediately.

## Algorithm

```
max_output_retries = self.resilience.max_output_retries
for attempt in 0 .. max_output_retries:
    result_text = self.turn(prompt, node.id, session_id_path, model=model, timeout=timeout,
                            prompt_path=prompt_path, budget_scale=budget_scale, base_timeout_s=base_timeout_s,
                            cwd=cwd, add_dirs=add_dirs, effort=effort,
                            invoke_retries=node.invoke_retries)
    try:
        outputs = extract_outputs(result_text, node)
        if validate is not None:
            validate(outputs)  # validation failures become OutputParseError
        return outputs
    except OutputParseError as exc:
        if attempt >= max_output_retries:
            raise
        print("⚠ output parse failed (attempt N/M): exc; retrying")
        prompt = retry_prompt(node, exc)   # next iteration reuses session_id_path unchanged
```

1. **Invoke.** [`turn`](agent-turn.md) runs one turn and returns its raw result text, or raises
   `BackendInvocationError` (propagated immediately — this loop only retries *parse* failures, not
   invocation failures; the transient and cap recoveries already happened one layer down).
2. **Parse and validate.** `extract_outputs(result_text, node)` turns the text into the node's
   declared outputs dict. When `validate` is supplied, it checks that dict against the caller's
   result shape; any validation exception is wrapped as `OutputParseError`, so an output with the
   required keys but invalid values receives the same recovery as malformed text. Success returns
   the outputs immediately.
3. **On `OutputParseError`, decide whether to retry in-session.** If this was the last allowed
   attempt (`attempt >= max_output_retries`), re-raise so the caller escalates. Otherwise log a
   warning and continue: `session_id_path` is untouched (the CLI turn that just ran already
   persisted it), so the next `turn` call **resumes** that same session rather than
   starting over.
4. **Build the corrective prompt.** [`retry_prompt(node, exc)`](retry-prompt.md) replaces `prompt`
   with a short nudge — "reply with ONLY a JSON object containing exactly these keys: […]" —
   naming `node.outputs`' keys and the parse or validation error, explicitly asking the agent not
   to redo any work (the session already has the prior turn's output attempt in context).
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
