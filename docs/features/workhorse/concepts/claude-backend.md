---
type: concept
slug: claude-backend
title: ClaudeBackend — the claude harness
---
# ClaudeBackend — the claude harness

The [AgentBackend](agent-backend.md) implementation for the Claude Code CLI (`claude -p`) — the
default backend, selected when [run](../workhorse.md#run)'s `--cli` (via
[get_backend](get-backend.md)) resolves to `claude` (or is left unset). Unlike the other four
implementations, it owns no protocol code itself: it is a thin **adapter** over the existing Claude
functions in `runner/agent.py` ([`_run_claude_cli`](run-claude-cli.md) / [`_compact_session`](compact-session.md)),
so those remain the single, tested implementation of the Claude `stream-json` / `--resume` /
`/compact` protocol rather than being duplicated into `backends.py`. It is the only backend with
`supports_compaction = True`; every other backend returns `False` from `compact` and relies on the
resilience ladder's reframe step instead.

- code: `workhorse/workhorse/runner/backends.py::ClaudeBackend`
- extends: [AgentBackend](agent-backend.md)
- verify: `workhorse/tests/test_backends.py::test_default_backend_is_claude`,
  `workhorse/tests/test_backends.py::test_claude_effort_maps_to_native_flag`,
  `workhorse/tests/test_backends.py::test_claude_no_effort_omits_flag`

## Contract

- `name` = `"claude"`.
- `default_model` = `"sonnet"` — the only backend with a usable built-in default; every other
  backend leaves `default_model` unset (`None`) and requires a node/config `model:` entry.
- `supports_compaction` = `True`.
- **`run_turn(prompt, node_id, session_id_path, model=None, timeout=DEFAULT_RESULT_TIMEOUT_S,
  cwd=None, add_dirs=None, effort=None)`** — delegates straight through to
  `_agent._run_claude_cli(prompt, node_id, session_id_path, model, timeout=timeout, cwd=cwd,
  add_dirs=add_dirs, effort=effort)`, forwarding every argument unchanged. Claude has a native
  reasoning-effort flag (`--effort low|medium|high|xhigh|max`), so `effort` passes straight through
  rather than being translated or clamped (contrast [CodexBackend](codex-backend.md), which clamps
  `xhigh`/`max` down to `high`, and [`_aider_effort`](aider-backend.md#_aider_effort), which clamps
  the same way). Raises `agent.BackendInvocationError` on failure, exactly as classified inside
  `_run_claude_cli`.
- **`compact(session_id_path, node_id, model=None, timeout=DEFAULT_RESULT_TIMEOUT_S)`** —
  delegates straight through to `_agent._compact_session(session_id_path, node_id, model)`. See
  [`_compact_session`](compact-session.md) for the full `/compact` algorithm; this method adds no
  logic of its own beyond the call.
- Imports the `agent` module (not its names) so test monkeypatches of
  `agent._run_claude_cli`/`agent._compact_session` are resolved at call time — `agent.py` only
  imports `backends` lazily (inside `run_agent`/`_invoke_claude`), so there is no import cycle to
  break by binding names at module-load time instead.

## Related pieces

- [`_run_claude_cli`](run-claude-cli.md) — the real implementation `run_turn` delegates to: builds
  the `claude --dangerously-skip-permissions --output-format stream-json --verbose
  [--model][--effort][--add-dir ...] -p [--resume <sid>]` argv, streams it, and classifies the
  result through [`classify_turn`](classify-turn.md).
- [`_compact_session`](compact-session.md) — the real implementation `compact` delegates to.
- [`get_backend`](get-backend.md) — resolves `"claude"` (or no `--cli`/`AGENT_CLI` at all) to a
  cached `ClaudeBackend()` instance.
- [`_invoke_claude`](invoke-claude.md) — Layer 1 of [run_agent](run-agent.md)'s resilience ladder;
  the caller of `run_turn` for every backend, Claude included.
- [CodexBackend](codex-backend.md) / [CopilotBackend](copilot-backend.md) /
  [OpenCodeBackend](opencode-backend.md) / [AiderBackend](aider-backend.md) — the four sibling
  implementations, each owning its own protocol code directly in `backends.py` rather than
  adapting into `agent.py`.
