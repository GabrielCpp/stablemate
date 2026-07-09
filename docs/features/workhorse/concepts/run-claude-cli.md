---
type: concept
slug: run-claude-cli
title: _run_claude_cli — the Claude CLI turn runner
---
# _run_claude_cli — the Claude CLI turn runner

The real implementation behind [ClaudeBackend.run_turn](claude-backend.md#contract) — builds the
`claude` CLI argv for one turn, resumes the node's persisted session if one exists, streams the
turn through `_stream_events`, and hands the raw result to
[`classify_turn`](classify-turn.md#ladder-first-match-wins) to turn into either the final result
text or a raised `BackendInvocationError`. Unlike the other four backends (which build their argv
and stream events directly inside `backends.py`), Claude's protocol code lives here in `agent.py`
so it stays the one, tested implementation `ClaudeBackend` adapts into rather than being duplicated.

- code: `workhorse/workhorse/runner/agent.py::_run_claude_cli`

## Contract

- **Input:**
  - `prompt: str` — the rendered prompt text, piped to the CLI over stdin (`stdin_data`).
  - `node_id: str` — used only for log-line prefixes (`[{node_id}] …`) and passed through to
    `_stream_events`/`classify_turn` for their own logging and error messages.
  - `session_id_path: Path | None` — the node's persisted `.session_id` file. When it exists and
    holds a non-blank id, the turn resumes that session (`--resume`); the file itself is read here
    inline (not via [`_read_session_id`](read-session-id.md), which the other three
    session-resuming backends share instead) and later (re)written by
    [`classify_turn`](classify-turn.md) via `_finalize_turn` on a successful or overflow turn.
  - `model: str | None` (default `None`) — when set, appended as `--model <model>`; when unset the
    CLI's own default model is used (`ClaudeBackend.default_model = "sonnet"` is applied by the
    caller before this point, not inside this function).
  - `timeout: float` (default `DEFAULT_RESULT_TIMEOUT_S`, env `AGENT_RESULT_TIMEOUT_S`, default
    `3600`) — maximum seconds to wait for a result event; forwarded to `_stream_events` (which
    forwards it to `stream_subprocess`'s watchdog) and to `classify_turn` (to decide whether a
    timeout is treated as transient).
  - `cwd: str | None` (default `None`) — working directory for the `claude` subprocess (controls
    `CLAUDE.md` discovery); forwarded to `_stream_events` as `cwd or None`.
  - `add_dirs: list[str] | None` (default `None`) — extra directories to grant the agent access to;
    each becomes its own `--add-dir <dir>` flag. `None` is treated the same as an empty list.
  - `effort: str | None` (default `None`) — Claude's native reasoning-effort flag value
    (`--effort low|medium|high|xhigh|max`); passed straight through with no clamping (contrast
    [CodexBackend](codex-backend.md) and [`_aider_effort`](aider-backend.md#_aider_effort), which
    clamp `xhigh`/`max` down to `high`).
- **Output:** `str` — the classified result text, exactly what
  [`classify_turn`](classify-turn.md#ladder-first-match-wins) returns on a successful turn.
- **Raises:** `BackendInvocationError` (via `classify_turn`), classified transient / scheduled-reset
  cap / context-overflow / non-recoverable per the shared ladder — this function performs no
  classification of its own beyond forwarding the raw signals.

## Algorithm

1. **Build the base argv:** `["claude", "--dangerously-skip-permissions", "--output-format",
   "stream-json", "--verbose"]`.
2. If `model` is truthy, extend with `["--model", model]`.
3. If `effort` is truthy, extend with `["--effort", effort]`.
4. For each directory in `add_dirs` (or `[]` if `None`), extend with `["--add-dir", d]` — one flag
   pair per directory, in the order given.
5. Append `"-p"` (prompt-from-stdin mode).
6. **Resume check:** if `session_id_path` is given and the file exists, read and strip its text; if
   the stripped id is non-empty, extend argv with `["--resume", sid]` and print
   `[{node_id}] 🔄 Resuming session: {sid[:8]}...`. A missing or blank file leaves the argv
   untouched — the turn starts a fresh session.
7. **Stream the turn:** call `_stream_events(cmd, node_id, timeout, stdin_data=prompt, cwd=cwd or
   None)`, which runs the argv through the shared supervised spawn path
   ([`stream_subprocess`](stream-subprocess.md)) and returns `(result_text, new_session_id,
   diagnostics, timed_out, rate_limited, rate_reset_at, returncode)`.
8. **Classify and return:** call
   `classify_turn("claude", node_id, result_text=result_text, diagnostics=diagnostics,
   timed_out=timed_out, returncode=returncode, timeout=timeout, session_id=new_session_id,
   session_id_path=session_id_path, rate_limited=rate_limited, rate_reset_at=rate_reset_at)` and
   return its result directly — this is the function's only return path; a failure raises out of
   `classify_turn` instead.

## Related pieces

- [ClaudeBackend.run_turn](claude-backend.md#contract) — the sole caller; delegates every argument
  straight through unchanged.
- [`classify_turn`](classify-turn.md#ladder-first-match-wins) — turns the raw
  `(result_text, diagnostics, timed_out, returncode, rate_limited, rate_reset_at)` tuple this
  function collects into either the returned text or a raised, classified
  `BackendInvocationError`; also persists `new_session_id` to `session_id_path` on success.
- [`_stream_events`](stream-events.md) — parses the `claude --output-format stream-json` line
  stream into the `(result_text, session_id, diagnostics, timed_out, rate_limited, rate_reset_at,
  returncode)` tuple this function unpacks; itself delegates the supervised subprocess spawn to
  [`stream_subprocess`](stream-subprocess.md).
- [`_read_session_id`](read-session-id.md) — the equivalent inline-resume lookup
  [CodexBackend](codex-backend.md), [CopilotBackend](copilot-backend.md), and
  [OpenCodeBackend](opencode-backend.md) share; this function performs the same
  read-strip-check logic inline instead, since it's the only backend with a `--resume <sid>` flag
  shaped this way.
- [`_compact_session`](compact-session.md) — the sibling Claude-protocol function in `agent.py`
  that `ClaudeBackend.compact` delegates to; not called by this function, but the other half of the
  Claude adapter's real implementation.
