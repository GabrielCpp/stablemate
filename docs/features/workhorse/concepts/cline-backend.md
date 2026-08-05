---
type: concept
slug: cline-backend
title: ClineBackend — the cline harness
---
# ClineBackend — the cline harness

The [AgentBackend](agent-backend.md) implementation for the Cline CLI (`cline --json`) — one of the
four JSONL-speaking backends alongside [CodexBackend](codex-backend.md),
[CopilotBackend](copilot-backend.md) and [OpenCodeBackend](opencode-backend.md). Selected when
[run](../workhorse.md#run)'s `--cli` (via [get_backend](get-backend.md)) resolves to `cline`; it is
never a default. Cline speaks plain chat-completions to whatever provider its model names, so it
drives OpenRouter models directly (e.g. `openrouter/example-org/example-model`) with **no proxy** — the OpenRouter-native role it shares
with [OpenCodeBackend](opencode-backend.md). The prompt is passed as a positional argv
message after `--` (not stdin); sessions resume by id via `--id`; it has no in-place compaction.
`run_turn` streams the CLI's event log through [the module's `_on_event`](cline-on-event.md), the
vocabulary callback that turns cline's own `run_result` / `hook_event` events into the turn's
result text, session id and usage.

Class and event callback live together in `runner/backends/cline.py` — one module per CLI, so
importing [the port](agent-backend.md) drags in no adapter.

- code: `workhorse/workhorse/runner/backends/cline.py::ClineBackend`
- extends: [AgentBackend](agent-backend.md)
- verify: `workhorse/tests/test_backends.py::test_cline_run_turn_fresh_then_resume`,
  `workhorse/tests/test_backends.py::test_cline_effort_passes_through_unmapped`,
  `workhorse/tests/test_backends.py::test_cline_unknown_effort_omits_the_flag`,
  `workhorse/tests/test_backends.py::test_non_claude_backends_registered`

## Contract

- `name` = `"cline"`.
- `default_model` = `None` — cline resolves its own model from the provider it was authenticated
  against, and naming a backend default here would silently override that.
- `supports_compaction` = `False`.
- **`run_turn(prompt, node_id, session_id_path, model=None, *, timeout, resilience, cwd=None,
  add_dirs=None, effort=None)`** — `timeout` and `resilience` are keyword-only and required
  ([why](agent-backend.md#run_turn-abstract)). Builds the argv:
  ```
  cline --json --auto-approve true --compaction basic
        [--model <model>] [--thinking <effort>] [--cwd <cwd>] [--id <sid>]
        -- <prompt>
  ```
  1. Read a persisted session id via [`read_session_id(session_id_path)`](read-session-id.md)
     (shared with the other JSONL backends).
  2. `--json` — headless NDJSON event stream, one `{"type": …, "ts": …}` envelope per line.
  3. `--auto-approve true` answers every tool prompt, so the turn is fully autonomous — the
     container is the sandbox.
  4. `--compaction basic` on every turn, so cline manages its own context window. This is *not* the
     ladder's compaction (see `compact` below).
  5. `--model <model>` only when the caller named one.
  6. `--thinking <effort>` only when `effort` is one of cline's own reasoning levels
     ([`_EFFORTS`](#_efforts)) — they are exactly workhorse's, so a recognized level passes through
     unmapped, unlike [codex](codex-backend.md)'s clamp or [opencode](opencode-backend.md)'s
     `--variant` names. An unrecognized level (`"max"`) omits the flag rather than guessing at a
     mapping the CLI would reject the whole turn over.
  7. `--cwd <cwd>` only when the caller named one. `add_dirs` has no cline equivalent — cline works
     the tree at `cwd` — and is ignored, so a multi-repo node must be given a `cwd` containing
     everything it needs.
  8. If a session id was read, append `--id <sid>` and log
     `[{node_id}] 🔄 Resuming cline session: {sid[:8]}...`.
  9. `-- <prompt>` — `--` ends option parsing so a prompt beginning with `-` is still read as the
     positional message, never as a flag.
  10. Stream the command through [`stream_jsonl`](stream-jsonl.md#contract) with
      [`_on_event`](cline-on-event.md) as the vocabulary callback and `stdin_data=None` (cline reads
      its message from argv, not stdin), forwarding `resilience=resilience`, `cwd=cwd` and
      `env_extra=self.harness_env()` → a [`TurnState`](finalize-turn.md#turnstate).
  11. Return [`finalize_turn`](finalize-turn.md)`("cline", node_id, state, session_id_path,
      timeout)` — raises [`BackendInvocationError`](classify-turn.md#backendinvocationerror) on
      failure, exactly as classified there.
- **`compact(session_id_path, node_id, model=None, *, timeout, resilience)`** — always returns
  `False`. Cline *has* a `--compaction` flag, but it configures cline's own automatic compaction
  for the turn, which is a different capability from the ladder's "compact this session and retry
  the same prompt". Claiming support would send the recovery ladder down a path with nothing behind
  it, so the ladder reframes on context overflow instead.

### `_EFFORTS`

- code: `workhorse/workhorse/runner/backends/cline.py::_EFFORTS`

The `frozenset` of levels cline's `--thinking` accepts — `none`, `low`, `medium`, `high`, `xhigh`.
It is a membership test rather than a mapping table because cline's range coincides with the
Claude-superset effort vocabulary everywhere except `max`, which is the one level that has to be
dropped.

## Related pieces

- [`read_session_id`](read-session-id.md) — reads the persisted `.session_id` file, if any, shared
  by every JSONL backend's `run_turn`.
- [`stream_jsonl`](stream-jsonl.md) — the shared JSONL event loop `run_turn` streams the `cline`
  invocation through; owns the process spawn, timeout, per-line dispatch to `on_event`, and the
  early-abort scan.
- [`_on_event`](cline-on-event.md) — the callback that knows cline's own event vocabulary and
  populates the turn's [`TurnState`](finalize-turn.md#turnstate); the terminal `run_result` is the
  richest usage report of any backend (tokens, cache split, real cost **and** duration).
- [`finalize_turn`](finalize-turn.md) — the shared classifier `run_turn` hands the finished
  `TurnState` to, turning it into the turn's result text or a raised `BackendInvocationError`.
- [`get_backend`](get-backend.md) — resolves `"cline"` to a cached `ClineBackend()` instance.
- [`CodexBackend`](codex-backend.md) / [`CopilotBackend`](copilot-backend.md) /
  [`OpenCodeBackend`](opencode-backend.md) — the other three JSONL backends sharing
  `stream_jsonl`/`finalize_turn`; opencode is the other OpenRouter-native one.
