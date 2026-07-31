---
type: concept
slug: compact-session
title: _compact_session — Claude's in-place context compaction
---
# _compact_session — Claude's in-place context compaction

Claude's implementation of [`AgentBackend.compact`](agent-backend.md#compact-abstract) — Layer 2
("compact & continue") of [the resilience ladder](run-agent.md#the-ladder). When a node's context
window is exhausted mid-run, [`AgentRunner`](agent-turn.md) calls `backend.compact(...)`;
[`ClaudeBackend`](claude-backend.md#contract) delegates straight through to this module-level
function, which resumes the node's persisted session and runs the CLI's `/compact` command in
place, so the node can retry its **same** prompt on a smaller session afterward instead of losing
its progress to a fresh-session reframe.

It is the only substantive implementation of Layer 2 in the tree. `compact` is
[abstract on the port](agent-backend.md#compact-abstract) — there is no inherited default — so the
other four backends each satisfy it with an unconditional `return False`, and their nodes always
fall through to reframe on overflow.

- code: `workhorse/workhorse/runner/backends/claude.py::_compact_session`
- verify: `workhorse/tests/test_config_harness_env.py::test_compaction_runs_under_the_same_env`

## Contract

- **Input:**
  - `session_id_path: Path | None` — the run's [`.session_id`](../run-artifacts.md#session_id)
    file for this node; the session to compact.
  - `node_id: str` — used only in log lines (`[{node_id}] ...`) and forwarded to
    [`stream_subprocess`](stream-subprocess.md#contract).
  - `model: str | None` (default `None`) — passed through as `--model` on the compaction call, so
    it runs on the same model as the node's own turns.
  - `resilience: AgentResilience` (**keyword-only, required**) — the run's tuning knobs, forwarded
    to `stream_subprocess` for the watchdog grace, heartbeat interval and exec-retry budget. No
    default, for [the same reason `run_turn` has none](agent-backend.md#run_turn-abstract): the
    `/compact` turn runs under the run's configuration, not the engine's.
  - `timeout: float` (**keyword-only, required**) — wall-clock budget for the `/compact` call,
    forwarded to `stream_subprocess`. There is no import-time constant behind this parameter; the
    caller supplies the same budget it uses for a normal turn.
  - `env_extra: dict[str, str] | None` (**keyword-only**, default `None`) — the operator's
    `[harness.claude].env` table, supplied by `ClaudeBackend.compact` as `self.harness_env()`. A
    knob that shapes a turn must also shape the `/compact` turn, or compaction runs under a
    different CLI configuration than the conversation it is compacting.
- **Output:** `bool` — `True` when compaction ran without itself overflowing (safe to retry the
  node's prompt on the now-smaller session); `False` when there is no session to compact, the
  call fails outright, or `/compact` reports failure. **Never raises** — compaction is
  best-effort, and every failure mode maps to `False` so the caller falls back to Layer 3
  (reframe) instead of crashing the node.

## Algorithm

1. **No-session short circuit.** If `session_id_path` is `None`, doesn't exist, or its contents
   strip to empty, return `False` immediately — there is nothing to compact (Layer 3 reframe
   handles this case).
2. **Build the compaction command.** `claude --dangerously-skip-permissions --output-format
   stream-json --verbose [--model <model>] --resume <sid> -p` — the same `-p --resume` headless
   invocation shape as a normal turn ([`_run_cli`](run-claude-cli.md#algorithm)), but with no
   `--add-dir` or `--effort` flags (compaction doesn't need tool access or a reasoning-effort
   override). Print `[{node_id}] 🗜 compacting session {sid[:8]}… to free context`.
3. **Stream `/compact` as the turn's stdin.** Runs the command through
   [`stream_subprocess`](stream-subprocess.md#algorithm) (own process group, watchdog, group-kill
   — a wedged compaction can't hang the run either) with `stdin_data="/compact"`,
   `resilience=resilience` and `env_extra=env_extra`, driving an `on_line` callback that
   accumulates a small dict of state as each JSON event arrives:
   - `event["session_id"]`, if present, updates `new_session_id` (starts seeded at the original
     `sid`, so the persisted id is never lost even if no event repeats it).
   - `event["status"] == "compacting"` sets `saw_compacting = True` — the CLI has acknowledged the
     command started.
   - `"compact_result" in event`:
     - `"failed"` → `compact_failed = True`, `compact_error = event.get("compact_error", "")`.
     - `"success"` → `saw_compacting = True` (also covers the case where a `"compacting"` status
       event was never seen but a terminal success was).
   - A blank line, or a line that isn't valid JSON, is silently skipped (best-effort parsing;
     unlike [`classify_turn`](classify-turn.md), a stray non-JSON line here doesn't count as a
     failure signal since compaction has no output-parsing step to fall back on).
   This function does **not** use [`_stream_events`](stream-events.md) or
   [`ClaudeTurnStream`](stream-events.md#claudeturnstream) — a `/compact` turn produces no result
   text to classify, so it reads the three fields it cares about itself rather than filling a
   turn accumulator it would then ignore.
4. **Call failure → `False`.** If `stream_subprocess` itself raises (a broad `except Exception`,
   deliberate and marked `noqa: BLE001` — compaction is best-effort and must never propagate a
   crash into the ladder), print `[{node_id}] ⚠ compaction call failed: {exc}` and return `False`
   without persisting anything.
5. **Persist the (possibly updated) session id.** Regardless of outcome, if `new_session_id` is
   non-empty, write it to `session_id_path` — the CLI may rotate the session id across a
   `/compact` call, and the next attempt must resume the id the compaction actually landed on.
6. **Resolve the verdict.** If `compact_failed`, print `[{node_id}] ⚠ compaction failed:
   {compact_error}` and return `False`. Otherwise return `saw_compacting` — `True` only if the CLI
   actually acknowledged or completed compaction, not merely because the call didn't crash.

## Verified behavior (Claude Code 2.1.x)

The headless CLI honors `/compact` in `-p --resume` mode (undocumented outside the CLI's own
stream-json event vocabulary) and reports the outcome via `system`/`status` events: a
`status: "compacting"` event, then a terminal event carrying `compact_result`
(`"success"`/`"failed"`, with `compact_error` on failure). The session id is preserved across the
call (confirmed by the `session_id` field on emitted events matching the original `sid`, though
`_compact_session` doesn't assume this and re-reads it from the events regardless).

## Related pieces

- [`ClaudeBackend.compact`](claude-backend.md#contract) — the sole caller; a single delegation
  that adds `env_extra=self.harness_env()` and forwards `resilience`/`timeout` unchanged.
- [the ladder](run-agent.md#the-ladder) — Layer 2 calls `backend.compact(...)` and, on `True`,
  retries the node's same prompt on the compacted session; on `False`, falls through to Layer 3
  (reframe). Bounded strictly by [`resilience.max_compact_attempts`](run-agent.md#the-ladder),
  which never eats into the reframe budget.
- [`AgentBackend.compact`](agent-backend.md#compact-abstract) — the abstract port method this
  implements; the four non-Claude backends (`codex`, `copilot`, `aider`, `opencode`) implement it
  as a bare `return False` and declare `supports_compaction = False`.
- [`stream_subprocess`](stream-subprocess.md) — the supervised-spawn path this call streams
  through, giving the `/compact` turn the same timeout/watchdog/group-kill guarantees as a normal
  node turn.
- [`classify_turn`](classify-turn.md) — detects the context-overflow condition on a node's
  *normal* turn that triggers Layer 2 in the first place; `_compact_session` itself does not call
  it — its own success/failure is read directly off the `compact_result` event.
- [`_run_cli`](run-claude-cli.md) — the sibling Claude-protocol function behind `run_turn`; shares
  this function's argv prefix and resume mechanics but classifies a result where this one does not.
