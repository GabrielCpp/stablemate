---
type: concept
slug: run-agent
title: run_agent — the agent-node resilience ladder
---
# run_agent — the agent-node resilience ladder

Runs one [`agent` node](../workflow-format.md#agent): renders its Jinja2 prompt, drives the
active [AgentBackend](agent-backend.md) through a turn, and extracts the node's declared
`outputs` — escalating through a four-layer resilience ladder instead of raising, because
[workflow execution](workflow.md#execution) calls it once per `agent` node of a run built to
survive unattended for days. [Workflow — Resilience](workflow.md#resilience-fail-soft) is the short summary
consumed by every reader of the graph; this node is the authoritative spec of that ladder.

The ladder delegates to a set of lower-level concept nodes documented on their own: a finished
turn is classified by [`classify_turn`](classify-turn.md) (called directly for Claude, or via the
shared adapter [`_finalize_turn`](finalize-turn.md) for every other backend); Layer 2 compacts
through [`_compact_session`](compact-session.md); Layer 3's reframe is built by
[`_rephrase_prompt`](rephrase-prompt.md), distinct from the same-session nudge
[`_retry_prompt`](retry-prompt.md) and the budget-overrun warning
[`_timeout_retry_prompt`](timeout-retry-prompt.md). One ladder attempt is driven by
[`_invoke_and_parse`](invoke-and-parse.md), which runs the turn via
[`_invoke_claude`](invoke-claude.md) (Layer 1's transient-retry/cap-wait, itself backed by
[`_sleep_with_notice`](sleep-with-notice.md), [`_cap_delay_seconds`](cap-delay-seconds.md), and
[`_parse_reset_seconds`](parse-reset-seconds.md)) and parses the result via
[`_extract_outputs`](extract-outputs.md). Every backend's turn streams through the
supervised-spawn path [`stream_subprocess`](stream-subprocess.md) — directly for Claude's
[`_stream_events`](stream-events.md)/[`_emit_event`](emit-event.md)/[`_tool_summary`](tool-summary.md)
live-echo, or via the shared [`_stream_jsonl`](stream-jsonl.md) loop for the JSONL backends — and
session continuity between turns is read back by [`_read_session_id`](read-session-id.md).

- code: `workhorse/workhorse/runner/agent.py::run_agent`
- verify: `workhorse/tests/test_agent_recovery.py::test_success_on_first_attempt_returns_outputs`,
  `workhorse/tests/test_agent_recovery.py::test_reframe_count_then_default`,
  `workhorse/tests/test_agent_recovery.py::test_overflow_compacts_then_continues_same_prompt`,
  `workhorse/tests/test_agent_recovery.py::test_non_recoverable_backend_error_aborts_without_reframe`,
  `workhorse/tests/test_node_timeout.py::test_timeout_defaults_to_1_hour`

## Contract

- **Input:**
  - `node: AgentNode` — the [agent node](../workflow-format.md#agent) to run.
  - `context: WorkflowContext` — the run's live [context](workflow-context.md); rendered to a
    dict once (`context.as_dict()`) as the Jinja base for the prompt/args.
  - `workflow_dir: Path` — base dir the prompt template path is resolved against.
  - `session_id_path: Path | None` — the run's [`.session_id`](../run-artifacts.md#session_id)
    file; `None` disables session persistence/resume entirely.
  - `max_output_retries: int` (default `DEFAULT_MAX_OUTPUT_RETRIES`, env `AGENT_MAX_OUTPUT_RETRIES`,
    default `2`) — same-session re-prompts when a turn's text can't be parsed into the outputs.
  - `max_rephrase_attempts: int` (default `DEFAULT_MAX_REPHRASE_ATTEMPTS`, env
    `AGENT_MAX_REPHRASE_ATTEMPTS`, default `3`) — fresh-session reframes before defaulting.
  - `max_compact_attempts: int` (default `DEFAULT_MAX_COMPACT_ATTEMPTS`, env
    `AGENT_MAX_COMPACT_ATTEMPTS`, default `2`) — `/compact`-and-continue tries on context overflow
    before falling through to reframe; `0` disables compaction recovery.
  - `resume_session: bool` (default `False`) — set only by the controller when re-entering a node
    that was killed mid-turn (not fast-forwarded); see [Sessions](#sessions).
- **Output:** `tuple[str, dict[str, Any]]` — `(rendered_prompt, outputs)`, the fully-rendered
  prompt text (for the `prompt.md` artifact) and the node's extracted/defaulted output dict (for
  `output.json` and the context merge) — see [run artifacts](../run-artifacts.md#node-idpromptmd).
- **Raises:** `BackendInvocationError` when a non-recoverable backend failure occurs, or when every
  layer of the ladder is exhausted and `AGENT_USE_DEFAULT_OUTPUTS=false`. Never raises for a
  recoverable failure while `USE_DEFAULT_OUTPUTS` is on — see [Layer 4](#layer-4-default-to-next).
  When this propagates out of `main.py`'s run loop, its top-level handler calls
  [`terminate_active`](stream-subprocess.md#terminate_active) to clean up the in-flight subprocess
  before the run exits.

## Setup (once, before the ladder)

1. **Timeout.** `effective_timeout = node.timeout or DEFAULT_RESULT_TIMEOUT_S` (env
   `AGENT_RESULT_TIMEOUT_S`, default `3600`); `node.timeout == float("inf")` (from
   [`timeout: infinity`](../workflow-format.md#agent)) short-circuits to `unbounded = True`, which
   the stream loops honor natively (`elapsed > inf` never trips) and which is surfaced to the
   prompt as the literal string `"unbounded"` rather than `int(inf)`.
2. **Render `cwd`.** `rendered_cwd = render_string(node.cwd, ctx)` if set, else `None`.
3. **Render `args` and build the prompt context.** `rendered_args = {k: render_string(v, ctx) for
   k, v in node.args.items()}`; merged with `ctx`, `node_timeout_s`/`node_timeout_min` (ints, or
   `"unbounded"`), and `_node_cwd` into `prompt_ctx`, then `rendered_prompt = render(node.prompt,
   prompt_ctx, workflow_dir)`.
4. **Echo the prompt summary** (template path + resolved variable values, not the rendered text)
   unless `WORKHORSE_PRINT_PROMPT` is `0`/`false`/`no`/empty. The full rendered prompt is still
   persisted verbatim to the run dir's `prompt.md`.
5. **Render `add_dirs`.** A bare-variable template (`"{{ some_list }}"`) resolves the native
   context list directly (Jinja2 would otherwise stringify it via `repr`); any other string
   template renders and is wrapped in a one-item list; a native `list[str]` renders each entry.
   Entries equal to the resolved `cwd` (by `Path.resolve()`) are dropped — the backend already
   passes `cwd` as the subprocess working directory, so re-granting it via `--add-dir` is
   redundant.
6. **Resolve the backend and model.** `backend = get_backend()` (the run's `--cli`/`AGENT_CLI`
   choice); `model, node_effort = _resolve_power_settings(node.power, backend.name, os.environ)`
   maps the node's abstract [`power:`](../workflow-format.md#agent) tier through
   [workhorse config](config.md#resolve_power), falling back to `AGENT_MODEL`/`AGENT_CLAUDE_MODEL`
   then `backend.default_model` if config leaves it unset.
7. **Session hygiene.** If `resume_session` is `False` and `session_id_path` exists, delete it —
   a fresh node must never inherit a previous node's `--resume` session (see
   [Sessions](#sessions)).

## The ladder

The setup above runs once; the loop below is the four-layer ladder, keyed by two counters:
`rephrase` (a genuine reframe — starts at `0`) and `compact_attempts` (starts at
`max_compact_attempts`, decremented on each compaction try). A context-compaction retry re-runs
the **same** prompt on the compacted session **without** consuming a reframe.

```
loop:
    prompt = rendered_prompt if rephrase == 0 else _rephrase_prompt(rendered_prompt, node, rephrase)
    if rephrase > 0: drop session_id_path (fresh session); log "🔄 reframing"
    try:
        outputs = _invoke_and_parse(prompt, node, session_id_path, model, max_output_retries,
                                     timeout=effective_timeout, cwd=rendered_cwd,
                                     add_dirs=rendered_add_dirs, effort=node_effort)
        return (rendered_prompt, outputs)
    except (BackendInvocationError, OutputParseError) as exc:
        # Layer 2 — compact & continue
        if exc is BackendInvocationError and exc.overflow and backend.supports_compaction
           and compact_attempts > 0:
            compact_attempts -= 1
            if backend.compact(session_id_path, node.id, model): continue   # retry same prompt
            # else: fall through to Layer 3 below
        # non-recoverable fast path
        if exc is BackendInvocationError and not exc.transient and not exc.overflow:
            raise
        # Layer 3 — reframe
        if rephrase < max_rephrase_attempts:
            sleep(min(10 * (rephrase + 1), 60))
            rephrase += 1
            continue
        # Layer 4 — default to next
        if USE_DEFAULT_OUTPUTS: return (rendered_prompt, _default_outputs(node))
        raise
```

1. **Transient retries** happen *inside* [`_invoke_and_parse`](invoke-and-parse.md)/[`_invoke_claude`](invoke-claude.md)
   (a distinct, lower-level layer — rate limits, overloads, network blips, timeouts, empty results,
   and scheduled-reset caps) before a `BackendInvocationError` ever reaches this loop; see
   [`_invoke_claude`](invoke-claude.md)/[`classify_turn`](classify-turn.md), governed by
   `AGENT_MAX_INVOKE_RETRIES` (default `4`) and the cap-wait knobs in
   `workhorse/docs/GUARDRAILS.md`.
2. **Compact & continue** — an `overflow=True` error (the model's context window was exhausted)
   is retried on the *same* session, summarized via the backend's `/compact`-equivalent
   (`_compact_session` for Claude), preserving the node's progress. Only attempted when
   `backend.supports_compaction` and `compact_attempts > 0`; a failed/ineffective compact call
   (`backend.compact(...)` returns `False`) falls through to reframe instead of retrying compaction
   again. Bounded strictly by `max_compact_attempts` — it never eats into the reframe budget.
3. **Reframe** — any other recoverable failure (transient-exhausted, or overflow with compaction
   unavailable) rephrases the prompt from scratch via [`_rephrase_prompt`](rephrase-prompt.md) and starts a **fresh**
   session (the prior, unhelpful exchange must not bias the retry), pausing
   `min(10 * (rephrase + 1), 60)` seconds first so a struggling service isn't hammered
   back-to-back. Up to `max_rephrase_attempts` times.
4. **Default to next** — once reframing is exhausted, and only when `USE_DEFAULT_OUTPUTS` (env
   `AGENT_USE_DEFAULT_OUTPUTS`, default `true`) is on, `_default_outputs(node)` returns
   `{spec.key: spec.default for spec in node.outputs}` — the workflow-declared fallback per
   [`OutputSpec.default`](../workflow-format.md#outputspec) (`null` if unset) — so the graph
   advances to `node.next` instead of the run aborting. Disabling the flag re-raises the last
   exception for a hard stop and manual resume.

**Non-recoverable fast path.** A `BackendInvocationError` that is neither `transient` nor
`overflow` (a crashed CLI, a hard server error) skips straight to re-raising — reframing can't
revive a dead CLI, and fabricating default outputs for a node that never really ran risks
corrupting the workflow (e.g. an empty `write_epic`). This check runs *before* the reframe/default
layers, so it overrides them regardless of how many attempts remain.

## Sessions

Each node runs its agent CLI with a **clean context** by default — node *N* never inherits node
*N − 1*'s conversation. `session_id_path` (the run's
[`.session_id`](../run-artifacts.md#session_id)) is:

- **dropped** before a node's first attempt, unless `resume_session=True` — the controller sets
  this only to continue *this same node* after a crash mid-node (a checkpointed-but-unfinished
  node re-entered on restart, not a normal forward move);
- **dropped again** on every reframe (Layer 3) — a reframed attempt is a deliberately fresh start;
- **preserved and reused** across a compaction retry (Layer 2) — that's the point of compacting
  instead of reframing: the node's in-session progress survives;
- **written** by the invocation layer (`classify_turn`) after every successful turn and after an
  overflow is detected (so the overflowing session can still be compacted).

## Related pieces

The ladder's own logic lives in `run_agent`; the following are separate mechanisms it calls into
(not yet modeled as their own concept nodes):

- [`_invoke_and_parse`](invoke-and-parse.md) — the same-session output-retry loop
  (`max_output_retries`) that precedes a reframe; itself calls [`_invoke_claude`](invoke-claude.md)
  for Layer-1 transient retry and cap-wait.
- [`classify_turn`](classify-turn.md) — the single failure classifier shared by every backend
  (transient / cap / overflow / non-recoverable / empty-result), described in
  `workhorse/docs/GUARDRAILS.md`.
- [`stream_subprocess`](stream-subprocess.md) and its watchdog (`_arm_watchdog`) — the
  supervised-spawn path (own process group, in-loop + out-of-band timeout, group-kill reap) every
  backend's CLI turn streams through. Its sibling
  [`terminate_active`](stream-subprocess.md#terminate_active) is what `main.py`'s top-level
  `KeyboardInterrupt`/`OutOfGasError`/`BackendInvocationError` handlers call to terminate the
  in-flight process when a run ends abnormally (see [Raises](#contract) above).
- [`_compact_session`](compact-session.md) — Claude's `/compact`-and-continue implementation of
  [`AgentBackend.compact`](agent-backend.md#contract).
- [`_extract_outputs`](extract-outputs.md) (strict then `json-repair`-tolerant `_parse_json_from_text`)
  — turns a turn's raw text into the node's declared `outputs` dict, raising `OutputParseError` on
  failure.
- [`_rephrase_prompt`](rephrase-prompt.md) — the fresh-session reframe strategy (Layer 3);
  [`_retry_prompt`](retry-prompt.md) / [`_timeout_retry_prompt`](timeout-retry-prompt.md) are the
  other two prompt-mutation strategies (a same-session output-retry nudge, and a budget-overrun
  warning fired from inside [`_invoke_claude`](invoke-claude.md) before a failure ever reaches this
  ladder).
- `_default_outputs` — Layer 4's fallback-output builder.
