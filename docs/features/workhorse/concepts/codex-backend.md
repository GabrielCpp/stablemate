---
type: concept
slug: codex-backend
title: CodexBackend — the codex harness
---
# CodexBackend — the codex harness

The [AgentBackend](agent-backend.md) implementation for OpenAI's `codex` CLI (`codex exec --json`)
— one of the three JSONL-speaking backends alongside [CopilotBackend](copilot-backend.md) and
[OpenCodeBackend](opencode-backend.md). Selected when [run](../workhorse.md#run)'s `--cli` (via
[get_backend](get-backend.md)) resolves to `codex`. Runs with the sandbox bypassed
(`--dangerously-bypass-approvals-and-sandbox`) because the worker container is itself the sandbox,
mirroring Claude's `--dangerously-skip-permissions`; the CLI has no in-place compaction, so the
resilience ladder reframes on context overflow instead. `run_turn` streams the CLI's event log
through [`_codex_on_event`](codex-on-event.md), the vocabulary callback that turns codex's own
`thread.started`/`item.completed` events into the turn's result text and session id.

- code: `workhorse/workhorse/runner/backends.py::CodexBackend`
- extends: [AgentBackend](agent-backend.md)
- verify: `workhorse/tests/test_backends.py::test_codex_run_turn_fresh_then_resume`,
  `workhorse/tests/test_backends.py::test_codex_effort_clamped_to_high`,
  `workhorse/tests/test_backends.py::test_codex_per_node_profile_overrides_env`,
  `workhorse/tests/test_backends.py::test_parse_codex_model`,
  `workhorse/tests/test_backends.py::test_non_claude_backends_registered`

## Contract

- `name` = `"codex"`.
- `default_model` = `None` — Codex's own configured default applies unless a node/profile names
  one.
- `supports_compaction` = `False`.
- **`run_turn(prompt, node_id, session_id_path, model=None, timeout=DEFAULT_RESULT_TIMEOUT_S,
  cwd=None, add_dirs=None, effort=None)`** — build the argv:
  ```
  codex [--profile <profile>] exec [resume <sid>] --json --skip-git-repo-check
        --dangerously-bypass-approvals-and-sandbox [-m <model_slug>]
        [-c model_reasoning_effort="<effort>"] -
  ```
  1. Read a persisted session id via [`_read_session_id(session_id_path)`](read-session-id.md).
  2. Resolve `(profile, model_slug)` from `model` via
     [`_parse_codex_model`](#_parse_codex_model). If the node named no profile, fall back to the
     `CODEX_PROFILE` env var (stripped; empty → `None`).
  3. `--profile <profile>` is a **top-level** flag — it must precede `exec` (and `exec resume`
     doesn't accept it at all) — so it goes in `head`, before the subcommand; only emitted when a
     profile was resolved.
  4. `--json --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox` are always present:
     JSON event streaming, skip codex's own "not a git repo" guard, and full sandbox/approval
     bypass (the container is the sandbox).
  5. `-m <model_slug>` only when step 2 resolved a model override.
  6. `-c model_reasoning_effort="<effort>"` only when the caller named an `effort` — a TOML
     config override (hence the quotes) since codex has no dedicated effort flag. Codex tops out
     at `"high"`, so `xhigh`/`max` are clamped down to `"high"` before being written; any other
     level is passed through verbatim.
  7. If a session id was read, the command is `codex [--profile P] exec resume <flags> <sid> -`
     (prompt still goes on stdin, not appended to the resume args) and logs
     `[{node_id}] 🔄 Resuming codex session: {sid[:8]}...`; otherwise `codex [--profile P] exec
     <flags> -`.
  8. `add_dirs` is accepted for interface parity with the other backends but has **no effect** —
     codex has no per-invocation extra-directory flag, so multi-repo dispatch isn't supported on
     this backend.
  9. Stream the command through [`_stream_jsonl`](stream-jsonl.md) with `prompt` as `stdin_data`
     (codex reads its prompt from stdin, via the trailing `-`) and
     [`_codex_on_event`](codex-on-event.md) as the vocabulary callback, forwarding `cwd` →
     `(state, diagnostics, timed_out, returncode)`.
  10. Return [`_finalize_turn`](finalize-turn.md)`("codex", node_id, state, diagnostics,
      timed_out, returncode, session_id_path, timeout)` — raises `agent.BackendInvocationError` on
      failure, exactly as classified there.
- **`compact(session_id_path, node_id, model=None, timeout=DEFAULT_RESULT_TIMEOUT_S)`** — always
  returns `False`: codex manages its own context internally (no in-place session compaction), so
  the resilience ladder reframes on context overflow instead.

### `_parse_codex_model`

- code: `workhorse/workhorse/runner/backends.py::_parse_codex_model`

Parses a node's `model:` string into `(profile, model_slug)`. Codex's per-node provider/model
selection is overloaded onto the generic `model` field as `<profile>[@<model-slug>]` — `@` is the
delimiter because it never appears in OpenRouter slugs (`deepseek/deepseek-chat-v3.1`) or local
tags (`qwen2.5-coder:32b`), which freely use `/` and `:`. A bare token (no `@`) is a **profile**
name — the unit a `~/.codex/config.toml` profile bundles provider+auth+model into.

- **Input:** `model: str | None`.
- **Output:** `tuple[str | None, str | None]` — `(profile, model_slug)`.
- **Algorithm:**
  1. Strip `model`; empty/`None` → `(None, None)`.
  2. If `@` is present, partition on the first one: `(profile_part.strip() or None,
     slug_part.strip() or None)`.
  3. Otherwise the whole stripped string is the profile: `(raw, None)`.
- **Examples:**

  | `model` | `(profile, model_slug)` |
  |---|---|
  | `"local"` | `(local, None)` — profile alone pins the model |
  | `"openrouter@deepseek/deep-v3.1"` | `(openrouter, deepseek/deep-v3.1)` |
  | `"openrouter@"` | `(openrouter, None)` |
  | `"@gpt-5.5"` | `(None, gpt-5.5)` — model only; profile falls back to `CODEX_PROFILE` |
  | `""` / `None` | `(None, None)` |

## Related pieces

- [`_read_session_id`](read-session-id.md) — reads the persisted `.session_id` file, if any, shared
  by every JSONL backend's `run_turn`.
- [`_stream_jsonl`](stream-jsonl.md) — the shared JSONL event loop `run_turn` streams the `codex`
  invocation through; owns the process spawn, timeout, and per-line dispatch to `on_event`.
- [`_codex_on_event`](codex-on-event.md) — the `on_event` callback that knows codex's own event
  vocabulary (`thread.started`/`item.completed`/error events) and populates `state`/`diagnostics`.
- [`_finalize_turn`](finalize-turn.md) — the shared classifier `run_turn` hands the finished stream
  to, turning it into the turn's result text or a raised `BackendInvocationError`.
- [`_codex_reset_at`](codex-reset-at.md) — a separate best-effort probe [OpenCodeBackend](opencode-backend.md)
  calls (not this backend) for the exact usage-cap reset time when a Codex-provider model hits a
  cap through OpenCode.
- [`get_backend`](get-backend.md) — resolves `"codex"` to a cached `CodexBackend()` instance.
- [`CopilotBackend`](copilot-backend.md) / [`OpenCodeBackend`](opencode-backend.md) — the other two
  JSONL backends sharing `_stream_jsonl`/`_finalize_turn`; [`AiderBackend`](aider-backend.md) is the
  plain-text sibling.
