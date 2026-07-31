---
type: concept
slug: run-claude-cli
title: _run_cli — the Claude CLI turn runner
---
# `_run_cli` — the Claude CLI turn runner

The implementation behind [`ClaudeBackend.run_turn`](claude-backend.md#contract): builds the
`claude` CLI argv for one turn, resumes the node's persisted session if one exists, streams the
turn through [`_stream_events`](stream-events.md), and hands the finished
[`ClaudeTurnStream`](stream-events.md#claudeturnstream) to
[`classify_turn`](classify-turn.md#ladder-first-match-wins) to become either the final result text
or a raised `BackendInvocationError`.

It is a **module-level function**, not a method — the class is a five-line delegation to it, and
the protocol lives here beside the other Claude-only symbols. Its old name, `_run_claude_cli`, was
qualified because it once sat in the CLI-agnostic ladder among functions belonging to no backend
in particular; one module per CLI supplies that disambiguation now, so it is simply `_run_cli`
(the same unqualification the other adapters' `_on_event` got).

- code: `workhorse/workhorse/runner/backends/claude.py::_run_cli`
- verify: `workhorse/tests/test_backends.py::test_claude_effort_maps_to_native_flag`,
  `workhorse/tests/test_backends.py::test_claude_no_effort_omits_flag`,
  `workhorse/tests/test_config_harness_env.py::test_every_backend_forwards_its_own_table`

## Contract

- **Input:**
  - `prompt: str` — the rendered prompt text, piped to the CLI over stdin (`stdin_data`).
  - `node_id: str` — used for log-line prefixes (`[{node_id}] …`) and passed through to
    `_stream_events`/`classify_turn` for their own logging and error messages.
  - `session_id_path: Path | None` — the node's persisted
    [`.session_id`](../run-artifacts.md#session_id) file. When it exists and holds a non-blank id,
    the turn resumes that session (`--resume`); the file itself is read here inline (not via
    [`read_session_id`](read-session-id.md), which the three JSONL backends share instead) and
    later (re)written by [`classify_turn`](classify-turn.md) on a successful or overflow turn.
  - `model: str | None` (default `None`) — when set, appended as `--model <model>`; when unset the
    CLI's own default applies (`ClaudeBackend.default_model = "sonnet"` is resolved by the caller
    before this point, not inside this function).
  - `resilience: AgentResilience` (**keyword-only, required**) — the run's tuning knobs, forwarded
    verbatim to [`stream_subprocess`](stream-subprocess.md#contract) via `_stream_events` for the
    watchdog grace, the heartbeat interval and the exec-retry budget. It carries no default, so
    nothing can quietly run a turn under import-time constants instead of the run's own
    configuration ([why](agent-backend.md#run_turn-abstract)).
  - `timeout: float` (**keyword-only, required**) — maximum seconds to wait for a result event;
    forwarded to `_stream_events` (and on to `stream_subprocess`'s watchdog) and to `classify_turn`
    (to decide whether a timeout is treated as transient). The default lives on the node, or on
    `AgentResilience.result_timeout_s`, not here — see
    [`timeout`](../workflow-format.md#timeout).
  - `cwd: str | None` (default `None`) — working directory for the `claude` subprocess (controls
    `CLAUDE.md` discovery); forwarded to `_stream_events` as `cwd or None`.
  - `add_dirs: list[str] | None` (default `None`) — extra directories to grant the agent access to;
    each becomes its own `--add-dir <dir>` flag. `None` is treated the same as an empty list.
  - `effort: str | None` (default `None`) — Claude's native reasoning-effort flag value
    (`--effort low|medium|high|xhigh|max`); passed straight through with no clamping (contrast
    [CodexBackend](codex-backend.md) and [`_aider_effort`](aider-backend.md#_aider_effort), which
    clamp `xhigh`/`max` down to `high`).
  - `env_extra: dict[str, str] | None` (**keyword-only**, default `None`) — the operator's
    `[harness.claude].env` table, supplied by
    [`ClaudeBackend.harness_env()`](agent-backend.md#harness_env-concrete) and layered over the
    inherited environment inside `stream_subprocess`.
- **Output:** `str` — the classified result text, exactly what
  [`classify_turn`](classify-turn.md#ladder-first-match-wins) returns on a successful turn.
- **Raises:** `BackendInvocationError` (via `classify_turn`), classified transient /
  scheduled-reset cap / context-overflow / non-recoverable per the shared ladder — this function
  performs no classification of its own beyond forwarding the raw signals.

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
7. **Stream the turn:** call `_stream_events(cmd, node_id, timeout, resilience=resilience,
   stdin_data=prompt, cwd=cwd or None, env_extra=env_extra)`, which runs the argv through the
   shared supervised spawn path ([`stream_subprocess`](stream-subprocess.md)) and returns a
   [`ClaudeTurnStream`](stream-events.md#claudeturnstream).
8. **Classify and return:** call `classify_turn("claude", node_id, …)` with the stream's fields
   read off **by name** — `result_text=stream.result_text`,
   `diagnostics=stream.diagnostics_text`, `timed_out=stream.timed_out`,
   `returncode=stream.returncode`, `timeout=timeout`, `session_id=stream.session_id`,
   `session_id_path=session_id_path`, `rate_limited=stream.rate_limited`,
   `rate_reset_at=stream.rate_reset_at` — and return its result directly. This is the function's
   only return path; a failure raises out of `classify_turn` instead.

Claude's structured cap signals (`rate_limited` / `rate_reset_at`, read off the stream-json
`rate_limit_event`) are passed in explicitly so a capped window still carries its precise reset
epoch into [the cap wait](cap-delay-seconds.md) rather than falling back to a blind default.

## Related pieces

- [`ClaudeBackend.run_turn`](claude-backend.md#contract) — the sole caller; forwards every argument
  unchanged and adds `env_extra=self.harness_env()`.
- [`_stream_events`](stream-events.md) — parses the `claude --output-format stream-json` line
  stream into the [`ClaudeTurnStream`](stream-events.md#claudeturnstream) this function reads;
  itself delegates the supervised subprocess spawn to [`stream_subprocess`](stream-subprocess.md).
- [`classify_turn`](classify-turn.md#ladder-first-match-wins) — turns the stream's raw signals into
  either the returned text or a classified, raised `BackendInvocationError`; also persists
  `session_id` to `session_id_path` on success.
- [`read_session_id`](read-session-id.md) — the equivalent resume lookup
  [CodexBackend](codex-backend.md), [CopilotBackend](copilot-backend.md) and
  [OpenCodeBackend](opencode-backend.md) share; this function performs the same
  read-strip-check logic inline instead, since it is the only backend with a `--resume <sid>` flag
  shaped this way.
- [`_compact_session`](compact-session.md) — the sibling Claude-protocol function that
  `ClaudeBackend.compact` delegates to; not called from here, but the other half of what this
  module owns.
