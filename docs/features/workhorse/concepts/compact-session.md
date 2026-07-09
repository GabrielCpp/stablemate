---
type: concept
slug: compact-session
title: _compact_session — Claude's in-place context compaction
---
# _compact_session — Claude's in-place context compaction

Claude's implementation of [`AgentBackend.compact`](agent-backend.md#contract) — Layer 2
("compact & continue") of [run_agent](run-agent.md)'s resilience ladder. When a node's context
window is exhausted mid-run, `run_agent` calls `backend.compact(...)`; [ClaudeBackend](agent-backend.md#implementations)
delegates straight through to this function, which resumes the node's persisted session and runs
the CLI's `/compact` command in place, so the node can retry its **same** prompt on a smaller
session afterward instead of losing its progress to a fresh-session reframe.

- code: `workhorse/workhorse/runner/agent.py::_compact_session`

## Contract

- **Input:**
  - `session_id_path: Path | None` — the run's [`.session_id`](../run-artifacts.md#session_id)
    file for this node; the session to compact.
  - `node_id: str` — used only in log lines (`[{node_id}] ...`).
  - `model: str | None` (default `None`) — passed through as `--model` on the compaction call, so
    it runs on the same model as the node's own turns.
  - `timeout: float` (default `DEFAULT_RESULT_TIMEOUT_S`) — wall-clock budget for the `/compact`
    call, forwarded to [`stream_subprocess`](stream-subprocess.md).
- **Output:** `bool` — `True` when compaction ran without itself overflowing (safe to retry the
  node's prompt on the now-smaller session); `False` when there is no session to compact, the
  call fails outright, or `/compact` reports failure. **Never raises** — compaction is
  best-effort, and every failure mode maps to `False` so the caller falls back to Layer 3
  (reframe) instead of crashing the node.

## Algorithm

1. **No-session short circuit.** If `session_id_path` is `None`, doesn't exist, or its contents
   are empty, return `False` immediately — there is nothing to compact (Layer 3 reframe handles
   this case).
2. **Build the compaction command.** `claude --dangerously-skip-permissions --output-format
   stream-json --verbose [--model <model>] --resume <sid> -p` — the same `-p --resume` headless
   invocation shape as a normal turn ([`_run_claude_cli`](run-agent.md)), but with no `--add-dir`
   or `--effort` flags (compaction doesn't need tool access or a reasoning-effort override).
3. **Stream `/compact` as the turn's stdin.** Runs the command through
   [`stream_subprocess`](stream-subprocess.md#algorithm) (own process group, watchdog, group-kill
   — a wedged compaction can't hang the run either) with `stdin_data="/compact"`, driving an
   `on_line` callback that accumulates state as each JSON event arrives:
   - `event["session_id"]`, if present, updates `new_session_id` (starts seeded at the original
     `sid`, so the persisted id is never lost even if no event repeats it).
   - `event["status"] == "compacting"` sets `saw_compacting = True` — the CLI has acknowledged the
     command started.
   - `"compact_result" in event`:
     - `"failed"` → `compact_failed = True`, `compact_error = event.get("compact_error", "")`.
     - `"success"` → `saw_compacting = True` (also covers the case where a `"compacting"` status
       event was never seen but a terminal success was).
   - A line that isn't valid JSON is silently skipped (best-effort parsing; unlike
     [`classify_turn`](classify-turn.md), a stray non-JSON line here doesn't count as a failure
     signal since compaction has no output-parsing step to fall back on).
4. **Call failure → `False`.** If `stream_subprocess` itself raises (broad `except Exception`,
   deliberate — compaction is best-effort and must never propagate a crash into the ladder), log
   and return `False` without persisting anything.
5. **Persist the (possibly updated) session id.** Regardless of outcome, if `new_session_id` is
   non-empty, write it to `session_id_path` — the CLI may rotate the session id across a
   `/compact` call, and the next attempt must resume the id the compaction actually landed on.
6. **Resolve the verdict.** If `compact_failed`, log the error and return `False`. Otherwise
   return `saw_compacting` — `True` only if the CLI actually acknowledged/completed compaction,
   not merely because the call didn't crash.

## Verified behavior (Claude Code 2.1.x)

The headless CLI honors `/compact` in `-p --resume` mode (undocumented outside the CLI's own
stream-json event vocabulary) and reports the outcome via `system`/`status` events: a
`status: "compacting"` event, then a terminal event carrying `compact_result`
(`"success"`/`"failed"`, with `compact_error` on failure). The session id is preserved across the
call (confirmed by the `session_id` field on emitted events matching the original `sid`, though
`_compact_session` doesn't assume this and re-reads it from the events regardless).

## Related pieces

- [run_agent](run-agent.md) — Layer 2 of the ladder; calls `backend.compact(...)` and, on `True`,
  retries the node's same prompt on the compacted session; on `False`, falls through to Layer 3
  (reframe). Bounded by `max_compact_attempts` (env `AGENT_MAX_COMPACT_ATTEMPTS`, default `2`).
- [`AgentBackend.compact`](agent-backend.md#contract) — the abstract contract this function
  implements for the `claude` backend; non-Claude backends (`codex`, `copilot`, `aider`,
  `opencode`) return `False` unconditionally (no in-place compaction), so their nodes always fall
  through to reframe on overflow.
- [`stream_subprocess`](stream-subprocess.md) — the supervised-spawn path this call streams
  through, giving the `/compact` turn the same timeout/watchdog/group-kill guarantees as a normal
  node turn.
- [`classify_turn`](classify-turn.md) — detects the context-overflow condition
  (`_is_context_overflow`) on a node's *normal* turn that triggers Layer 2 in the first place;
  `_compact_session` itself does not call it — its own success/failure is read directly off the
  `compact_result` event.
