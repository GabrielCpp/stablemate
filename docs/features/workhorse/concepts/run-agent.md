---
type: concept
slug: run-agent
title: AgentRunner.run — the agent-node resilience ladder
---
# AgentRunner.run — the agent-node resilience ladder

Runs one [`agent` turn](../workflow-format.md#the-agent-turn): renders its Jinja2 prompt, drives the
run's [AgentBackend](agent-backend.md) through a turn, and extracts the node's declared
`returns` — escalating through a four-layer resilience ladder instead of raising, because
[`drive`](pyflow-driver.md) reaches it once per agent turn of a run built to survive unattended
for days. Every other page that says workhorse is "fail-soft" is summarising this one; this node
is the authoritative spec of that ladder.

`AgentRunner` is a **frozen dataclass service**, not a free function. Its fields are the things one
whole run shares — the backend to drive, the [`AgentResilience`](#the-runner) knobs to drive it
with, the [`Clock`](#the-runner) to wait on — so what varies per node is a parameter of `run` and
no caller forwards the run's configuration field by field.

The ladder delegates to a set of lower-level concept nodes documented on their own: a finished
turn is classified by [`classify_turn`](classify-turn.md) (called directly for Claude, or via the
shared adapter [`finalize_turn`](finalize-turn.md) for every other backend); Layer 2 compacts
through [`_compact_session`](compact-session.md); Layer 3's reframe is built by
[`rephrase_prompt`](rephrase-prompt.md), distinct from the same-session nudge
[`retry_prompt`](retry-prompt.md) and the budget-overrun warning
[`timeout_retry_prompt`](timeout-retry-prompt.md). One ladder attempt is driven by
[`_invoke_and_parse`](invoke-and-parse.md), which runs the turn via
[`turn`](agent-turn.md) (Layer 1's transient-retry/cap-wait, itself backed by
[`sleep_with_notice`](sleep-with-notice.md), [`cap_delay_seconds`](cap-delay-seconds.md), and
[`parse_reset_seconds`](parse-reset-seconds.md)) and parses the result via
[`extract_outputs`](extract-outputs.md). Every backend's turn streams through the
supervised-spawn path [`stream_subprocess`](stream-subprocess.md) — directly for Claude's
[`_stream_events`](stream-events.md)/[`_emit_event`](emit-event.md)/[`_tool_summary`](tool-summary.md)
live-echo, or via the shared [`stream_jsonl`](stream-jsonl.md) loop for the JSONL backends — and
session continuity between turns is read back by [`read_session_id`](read-session-id.md).

- code: `workhorse/workhorse/runner/ladder.py::AgentRunner.run`
- verify: `workhorse/tests/test_agent_recovery.py::test_success_on_first_attempt_returns_outputs`,
  `workhorse/tests/test_agent_recovery.py::test_reframe_count_then_default`,
  `workhorse/tests/test_agent_recovery.py::test_overflow_compacts_then_continues_same_prompt`,
  `workhorse/tests/test_agent_recovery.py::test_non_recoverable_backend_error_aborts_without_reframe`,
  `workhorse/tests/test_agent_recovery.py::test_rendered_prompt_is_written_and_only_path_is_printed`,
  `workhorse/tests/test_node_timeout.py::test_timeout_defaults_to_1_hour`

## The runner

The dataclass holds what the whole run shares. Every field is injected — nothing below the CLI
boundary reads the environment, which is what lets an in-process test state a one-attempt budget
or sleep through an eight-day cap window in microseconds.

- `backend: AgentBackend` — the adapter for the run's chosen CLI. **The backend is injected, never
  resolved here.** `AGENT_CLI` is read once at the CLI boundary and the chosen adapter is handed
  down, so the ladder names no CLI and imports none — the reason the ladder and `backends` no
  longer have to import each other lazily.
- `resilience: AgentResilience` — every `AGENT_*` retry/cap/timeout knob as a field, built by
  `AgentResilience.from_env` at the same boundary. The env-var names and defaults are documented
  operator-side in [GUARDRAILS.md](../../../../workhorse/docs/GUARDRAILS.md); this ladder reads
  only the fields.
- `clock: Clock` — `now()` and `sleep()`, the only two things the ladder does with time. Defaults
  to `SYSTEM_CLOCK`; a `FakeClock` is what makes cap-wait tests instant.
- `print_prompt: bool` (default `True`, from `WORKHORSE_PRINT_PROMPT`) — whether to echo each
  node's rendered-prompt **path** to the console.
- `model_override: str | None` — the run-level `AGENT_MODEL`/`AGENT_CLAUDE_MODEL` fallback, already
  resolved from the environment.

`AgentRunner.from_config(config, *, clock=SYSTEM_CLOCK)` is **the one construction point**: it turns
the run's `RunConfig` (`workhorse/workhorse/config_run.py`, built once from the environment at the
CLI boundary) into the service the engine calls. Tests build the dataclass directly, or substitute
a stand-in entirely via `RunEnv(agent_runner=...)` — see [testing](testing.md).

## Contract

- **Input:**
  - `node: AgentNode` — the [agent turn](../workflow-format.md#the-agent-turn) to run.
  - `context: WorkflowContext` — the run's live [context](workflow-context.md); rendered to a
    dict once (`context.as_dict()`) as the Jinja base for the prompt/args.
  - `workflow_dir: Path` — base dir the prompt template path is resolved against.
  - `session_id_path: Path | None` — the run's [`.session_id`](../run-artifacts.md#session_id)
    file; `None` disables session persistence/resume entirely.
  - `resume_session: bool` (keyword-only, default `False`) — set only by the driver when
    re-entering a node that was killed mid-turn (not fast-forwarded); see [Sessions](#sessions).
  - `run_dir: Path | None` (keyword-only, default `None`) — where to persist the rendered prompt
    before invoking, as `<run_dir>/<node.id>/prompt.md`. `None` skips both the write and the
    console echo.
- **Output:** `tuple[str, dict[str, Any]]` — `(rendered_prompt, outputs)`, the fully-rendered
  prompt text and the node's extracted/defaulted output dict (for `output.json` and the context
  merge) — see [run artifacts](../run-artifacts.md#node-idpromptmd).
- **Raises:** `BackendInvocationError` when a non-recoverable backend failure occurs, or when every
  layer of the ladder is exhausted and `resilience.use_default_outputs` is off. Never raises for a
  recoverable failure while that flag is on — see [Layer 4](#the-ladder).
  It is a `RuntimeError`, **not** a `PyflowError`, so it propagates all the way out of
  `pyflow/run.py`'s driver call without passing either of that module's two cleanup handlers — see
  [Related pieces](#related-pieces).

The counters the ladder is tuned by are **not** parameters — they are `resilience` fields:
`max_output_retries`, `max_invoke_retries`, `max_rephrase_attempts`, `max_compact_attempts`,
`use_default_outputs`, `result_timeout_s`.

## Setup (once, before the ladder)

1. **Timeout.** `effective_timeout = node.timeout or resilience.result_timeout_s` (default
   `3600`); `node.timeout == float("inf")` (from
   [`timeout: infinity`](../workflow-format.md#timeout)) short-circuits to `unbounded = True`, which
   the stream loops honor natively (`elapsed > inf` never trips) and which is surfaced to the
   prompt as the literal string `"unbounded"` rather than `int(inf)`.
2. **Render `cwd`.** `rendered_cwd = render_string(node.cwd, ctx).strip()` if set, else `None`.
3. **Render `args` and build the prompt context.** `rendered_args = {k: render_string(v, ctx) for
   k, v in node.args.items()}`; merged with `ctx`, `node_timeout_s`/`node_timeout_min` (ints, or
   `"unbounded"`), and `_node_cwd` into `prompt_ctx`, then `rendered_prompt = render(node.prompt,
   prompt_ctx, workflow_dir)`.
4. **Persist the prompt, echo only its path.** `_write_prompt_for_inspection` writes the fully
   rendered text to `<run_dir>/<node.id>/prompt.md` *before* the agent is launched, so even a node
   that crashes mid-turn is inspectable. The console gets one line — `[<node>] prompt: <path>` —
   and never the rendered variables, which is why a prompt carrying a secret or a wall of context
   is safe to log. Suppressed by `print_prompt=False` (`WORKHORSE_PRINT_PROMPT=0`); with
   `run_dir=None` neither the write nor the echo happens.
5. **Render `add_dirs`.** A bare-variable template (`"{{ some_list }}"`) resolves the native
   context list directly (Jinja2 would otherwise stringify it via `repr`); any other string
   template renders and is wrapped in a one-item list; a native `list[str]` renders each entry.
   Entries equal to the resolved `cwd` (by `Path.resolve()`) are dropped — the backend already
   passes `cwd` as the subprocess working directory, so re-granting it via `--add-dir` is
   redundant.
6. **Resolve the model and effort.** `model, node_effort = _resolve_power_settings(node.power,
   self.backend.name, self.model_override)` maps the node's abstract
   [`power:`](../workflow-format.md#power) tier through
   [config](config.md#resolve_power), falling back per field to the run-level `model_override`
   then the config's `[default.<backend>]` table, and finally to `backend.default_model`. The
   backend itself is **not** resolved here: it was injected at construction.
7. **Session hygiene.** If `resume_session` is `False` and `session_id_path` exists, delete it —
   a fresh node must never inherit a previous node's `--resume` session (see
   [Sessions](#sessions)).

## The ladder

The setup above runs once; the loop below is the four-layer ladder, keyed by two counters:
`rephrase` (a genuine reframe — starts at `0`) and `compact_attempts` (starts at
`resilience.max_compact_attempts`, decremented on each compaction try). A context-compaction retry
re-runs the **same** prompt on the compacted session **without** consuming a reframe.

```
loop:
    prompt = rendered_prompt if rephrase == 0 else rephrase_prompt(rendered_prompt, node, rephrase)
    if rephrase > 0: drop session_id_path (fresh session); log "🔄 reframing"
    try:
        outputs = self._invoke_and_parse(prompt, node, session_id_path, model,
                                          timeout=effective_timeout, cwd=rendered_cwd,
                                          add_dirs=rendered_add_dirs, effort=node_effort)
        return (rendered_prompt, outputs)
    except (BackendInvocationError, OutputParseError) as exc:
        # Layer 2 — compact & continue
        if exc is BackendInvocationError and exc.overflow and self.backend.supports_compaction
           and compact_attempts > 0:
            compact_attempts -= 1
            if self.backend.compact(session_id_path, node_id, model,
                                    timeout=resilience.result_timeout_s,
                                    resilience=resilience): continue   # retry same prompt
            # else: fall through to Layer 3 below
        # non-recoverable fast path
        if exc is BackendInvocationError and not exc.transient and not exc.overflow:
            raise
        # Layer 3 — reframe
        if rephrase < resilience.max_rephrase_attempts:
            self.clock.sleep(min(10 * (rephrase + 1), 60))
            rephrase += 1
            continue
        # Layer 4 — default to next
        if resilience.use_default_outputs: return (rendered_prompt, default_outputs(node))
        raise
```

1. **Transient retries** happen *inside* [`_invoke_and_parse`](invoke-and-parse.md)/[`turn`](agent-turn.md)
   (a distinct, lower-level layer — rate limits, overloads, network blips, timeouts, empty results,
   and scheduled-reset caps) before a `BackendInvocationError` ever reaches this loop; see
   [`turn`](agent-turn.md)/[`classify_turn`](classify-turn.md), governed by
   `resilience.max_invoke_retries` (default `4`) and the cap-wait knobs in
   `workhorse/docs/GUARDRAILS.md`.
2. **Compact & continue** — an `overflow=True` error (the model's context window was exhausted)
   is retried on the *same* session, summarized via the backend's `/compact`-equivalent
   (`_compact_session` for Claude), preserving the node's progress. Only attempted when
   `backend.supports_compaction` and `compact_attempts > 0`; a failed/ineffective compact call
   (`backend.compact(...)` returns `False`) falls through to reframe instead of retrying compaction
   again. Bounded strictly by `resilience.max_compact_attempts` — it never eats into the reframe
   budget. Emits an otel `compact` turn event per attempt.
3. **Reframe** — any other recoverable failure (transient-exhausted, or overflow with compaction
   unavailable) rephrases the prompt from scratch via [`rephrase_prompt`](rephrase-prompt.md) and
   starts a **fresh** session (the prior, unhelpful exchange must not bias the retry), pausing
   `min(10 * (rephrase + 1), 60)` seconds first — on the **injected clock**, so this pause costs a
   test nothing — so a struggling service isn't hammered back-to-back. Up to
   `resilience.max_rephrase_attempts` times, with an otel `reframe` event each.
4. **Default to next** — once reframing is exhausted, and only when
   `resilience.use_default_outputs` (env `AGENT_USE_DEFAULT_OUTPUTS`, default `true`) is on,
   [`default_outputs(node)`](#related-pieces) returns `{spec.key: spec.default for spec in
   node.outputs}` — the workflow-declared fallback per
   [`OutputSpec.default`](../workflow-format.md#returns) (`None` if unset) — so the run
   advances to the next state instead of aborting, with an otel `default_outputs` error event.
   Disabling the flag re-raises the last exception for a hard stop and manual resume.

**Non-recoverable fast path.** A `BackendInvocationError` that is neither `transient` nor
`overflow` (a crashed CLI, a hard server error) skips straight to re-raising — reframing can't
revive a dead CLI, and fabricating default outputs for a node that never really ran risks
corrupting the workflow (e.g. an empty `write_epic`). This check runs *before* the reframe/default
layers, so it overrides them regardless of how many attempts remain.

## Sessions

Each node runs its agent CLI with a **clean context** by default — node *N* never inherits node
*N − 1*'s conversation. `session_id_path` (the run's
[`.session_id`](../run-artifacts.md#session_id)) is:

- **dropped** before a node's first attempt, unless `resume_session=True` — the driver sets
  this only to continue *this same node* after a crash mid-node (a checkpointed-but-unfinished
  node re-entered on restart, not a normal forward move);
- **dropped again** on every reframe (Layer 3) — a reframed attempt is a deliberately fresh start;
- **preserved and reused** across a compaction retry (Layer 2) — that's the point of compacting
  instead of reframing: the node's in-session progress survives;
- **written** by the invocation layer (`classify_turn`) after every successful turn and after an
  overflow is detected (so the overflowing session can still be compacted).

## Related pieces

The ladder's own logic lives in `AgentRunner.run`; the following are separate mechanisms it calls
into, each in its own module under `workhorse/workhorse/runner/`:

- [`AgentRunner._invoke_and_parse`](invoke-and-parse.md) — the same-session output-retry loop
  (`resilience.max_output_retries`) that precedes a reframe; itself calls
  [`AgentRunner.turn`](agent-turn.md) for Layer-1 transient retry and cap-wait.
- [`classify_turn`](classify-turn.md) (`runner/failure.py`) — the single failure classifier shared
  by every backend (transient / cap / overflow / non-recoverable / empty-result), described in
  `workhorse/docs/GUARDRAILS.md`.
- [`stream_subprocess`](stream-subprocess.md) and its watchdog (`runner/process.py`) — the
  supervised-spawn path (own process group, in-loop + out-of-band timeout, group-kill reap) every
  backend's CLI turn streams through. Its sibling
  [`terminate_active`](stream-subprocess.md#terminate_active) is what `pyflow/run.py` calls to
  terminate the in-flight process when a run ends abnormally. It wraps its `drive(wf, env, resume)`
  call in exactly two handlers: `KeyboardInterrupt` (terminate, record the interrupt, print the
  `--resume-run` line, `SystemExit(130)`) and `PyflowError` (terminate, then mark the run `fail` and
  leave the run dir resumable). A `BackendInvocationError` is neither — it is a plain `RuntimeError`
  — so an exhausted ladder unwinds past both and the subprocess is reaped by process-group exit
  rather than by this call (see [Raises](#contract) above).
- [`_compact_session`](compact-session.md) — Claude's `/compact`-and-continue implementation of
  [`AgentBackend.compact`](agent-backend.md#contract).
- [`extract_outputs`](extract-outputs.md) (`runner/extract.py`; strict then `json-repair`-tolerant
  `parse_json_from_text`) — turns a turn's raw text into the node's declared outputs dict, raising
  `OutputParseError` on failure.
- [`rephrase_prompt`](rephrase-prompt.md) — the fresh-session reframe strategy (Layer 3);
  [`retry_prompt`](retry-prompt.md) / [`timeout_retry_prompt`](timeout-retry-prompt.md) are the
  other two prompt-mutation strategies (a same-session output-retry nudge, and a budget-overrun
  warning fired from inside [`turn`](agent-turn.md) before a failure ever reaches this ladder).
  All three, plus Layer 4's `default_outputs`, live in `runner/reframe.py`.
- `Clock` / `SYSTEM_CLOCK` (`runner/clock.py`) — the two-method protocol (`now`, `sleep`) the
  ladder and the cap-wait helpers are handed instead of importing `time`.
