---
type: concept
slug: copilot-backend
title: CopilotBackend — the copilot harness
---
# CopilotBackend — the copilot harness

The [AgentBackend](agent-backend.md) implementation for the GitHub Copilot CLI (`copilot -p
--output-format json`) — one of the four JSONL-speaking backends alongside
[CodexBackend](codex-backend.md), [ClineBackend](cline-backend.md) and
[OpenCodeBackend](opencode-backend.md). Selected when
[run](../workhorse.md#run)'s `--cli` (via [get_backend](get-backend.md)) resolves to `copilot`.
`--allow-all --no-ask-user` make every turn fully autonomous — no interactive confirmation, since
the container is the sandbox — and the CLI has no in-place compaction, so the resilience ladder
reframes on context overflow instead. `run_turn` streams the CLI's event log through
[the module's `_on_event`](copilot-on-event.md), the vocabulary callback that turns Copilot's own
`assistant.message` / `result` events into the turn's result text, session id and token usage.

Class and event callback live together in `runner/backends/copilot.py` — one module per CLI, so
importing [the port](agent-backend.md) drags in no adapter.

- code: `workhorse/workhorse/runner/backends/copilot.py::CopilotBackend`
- extends: [AgentBackend](agent-backend.md)
- verify: `workhorse/tests/test_backends.py::test_copilot_run_turn_fresh_then_resume`,
  `workhorse/tests/test_backends.py::test_copilot_effort_maps_to_native_flag`,
  `workhorse/tests/test_backends.py::test_non_claude_backends_registered`

## Contract

- `name` = `"copilot"`.
- `default_model` = `None` — Copilot's own default (`'auto'`) applies unless a node names one.
- `supports_compaction` = `False`.
- **`run_turn(prompt, node_id, session_id_path, model=None, *, timeout, resilience, cwd=None,
  add_dirs=None, effort=None)`** — `timeout` and `resilience` are keyword-only and required
  ([why](agent-backend.md#run_turn-abstract)). Builds the argv:
  ```
  copilot -p <prompt> --output-format json --allow-all --no-ask-user
          [--model <model>] [--effort <effort>]
          [--add-dir <dir> ...] [--session-id <sid>]
  ```
  1. Read a persisted session id via [`read_session_id(session_id_path)`](read-session-id.md).
  2. `-p <prompt>` — Copilot takes the prompt as a `-p` arg, not on stdin (unlike Codex's
     resume-with-prompt path).
  3. `--output-format json --allow-all --no-ask-user` are always present: JSON streaming, full tool
     autonomy, no interactive prompts.
  4. `--model <model>` only when the caller named one.
  5. `--effort <effort>` only when the caller named one — Copilot has a native reasoning-effort
     flag spanning the same level range as Claude's, passed through verbatim with no clamping (in
     contrast to [codex](codex-backend.md), which tops out at `high`, and
     [cline](cline-backend.md#_efforts), which drops a `max` it has no level for).
  6. `--add-dir <dir>` once per entry in `add_dirs` — Copilot's own path sandbox only allows CWD,
     its subdirs, and the temp dir by default, so multi-repo dispatch (a node whose `cwd` is one
     service repo but that also needs to read/write a sibling repo) needs each extra directory
     granted explicitly. Even though `--allow-all` disables the sandbox check itself, the granted
     dirs still inform Copilot where to look for project instructions (skill/`CLAUDE.md`
     discovery).
  7. If a session id was read, append `--session-id <sid>` and log
     `[{node_id}] 🔄 Resuming copilot session: {sid[:8]}...`.
  8. Stream the command through [`stream_jsonl`](stream-jsonl.md#contract) with
     [`_on_event`](copilot-on-event.md) as the vocabulary callback and `stdin_data=None` (no stdin
     channel), forwarding `resilience=resilience`, `cwd=cwd` and
     `env_extra=self.harness_env()` → a [`TurnState`](finalize-turn.md#turnstate).
  9. Return [`finalize_turn`](finalize-turn.md)`("copilot", node_id, state, session_id_path,
     timeout)` — raises [`BackendInvocationError`](classify-turn.md#backendinvocationerror) on
     failure, exactly as classified there.
- **`compact(session_id_path, node_id, model=None, *, timeout, resilience)`** — always returns
  `False`: Copilot has no in-place session compaction, so the resilience ladder reframes on
  context overflow instead.

## Related pieces

- [`read_session_id`](read-session-id.md) — reads the persisted `.session_id` file, if any, shared
  by every JSONL backend's `run_turn`.
- [`stream_jsonl`](stream-jsonl.md) — the shared JSONL event loop `run_turn` streams the `copilot`
  invocation through; owns the process spawn, timeout, per-line dispatch to `on_event`, and the
  early-abort scan.
- [`_on_event`](copilot-on-event.md) — the callback that knows Copilot's own event vocabulary and
  populates the turn's [`TurnState`](finalize-turn.md#turnstate).
- [`finalize_turn`](finalize-turn.md) — the shared classifier `run_turn` hands the finished
  `TurnState` to, turning it into the turn's result text or a raised `BackendInvocationError`.
- [`get_backend`](get-backend.md) — resolves `"copilot"` to a cached `CopilotBackend()` instance.
- [`CodexBackend`](codex-backend.md) / [`ClineBackend`](cline-backend.md) /
  [`OpenCodeBackend`](opencode-backend.md) — the other three JSONL backends sharing
  `stream_jsonl`/`finalize_turn`.
