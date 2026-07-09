---
type: concept
slug: aider-backend
title: AiderBackend — the aider harness
---
# AiderBackend — the aider harness

The [AgentBackend](agent-backend.md) implementation for the `aider` CLI (`aider --message`) — a
single-message, non-interactive coder with no event stream and no resumable session, unlike the
three JSONL backends ([CodexBackend](codex-backend.md), [CopilotBackend](copilot-backend.md),
[OpenCodeBackend](opencode-backend.md)). Selected when [run](../workhorse.md#run)'s `--cli` (via
[get_backend](get-backend.md)) resolves to `aider`. It speaks plain chat-completions via litellm,
so it drives OpenRouter models directly
(e.g. `openrouter/xiaomi/mimo-v2.5`) with no proxy — the OpenRouter provider pin and prompt caching
for the MiMo experiment live in aider's own model-settings file, not here.

- code: `workhorse/workhorse/runner/backends.py::AiderBackend`
- extends: [AgentBackend](agent-backend.md)

## Contract

- `name` = `"aider"`.
- `default_model` = `None` — aider has no usable default; the node's `model:` map must name one.
- `supports_compaction` = `False`.
- **`run_turn(prompt, node_id, session_id_path, model=None, timeout=DEFAULT_RESULT_TIMEOUT_S,
  cwd=None, add_dirs=None, effort=None)`** — build the argv:
  ```
  aider --message <prompt> --yes-always --no-stream --no-pretty --no-auto-commits
        --no-gitignore --no-analytics --no-show-model-warnings --no-check-model-accepts-settings
        [--model <model>] [--reasoning-effort <_aider_effort(effort)>]
  ```
  - `--yes-always` answers every interactive prompt so the run stays non-interactive.
  - `--no-stream --no-pretty` give clean, line-buffered stdout for
    [`_run_text_turn`](run-text-turn.md) to capture.
  - `--no-auto-commits --no-gitignore` keep aider from mutating the repo's git state or
    `.gitignore` behind the caller's back.
  - `--model` is set only when the node named one (there is no backend default to fall back to).
  - `--reasoning-effort` is set only when the node named an `effort`, translated through
    [`_aider_effort`](#_aider_effort).
  - `add_dirs` has no aider equivalent — aider always works the repo at `cwd` — and is silently
    ignored.
  - Delegates the actual spawn/classification to
    [`_run_text_turn("aider", cmd, node_id, timeout, cwd, session_id_path)`](run-text-turn.md): the
    whole stdout transcript becomes the turn's result text (and, doubling as the diagnostics
    channel, is what [`_finalize_turn`](finalize-turn.md) scans for overflow/transient markers).
    Raises `agent.BackendInvocationError` on failure, exactly as classified there.
- **`compact(session_id_path, node_id, model=None, timeout=DEFAULT_RESULT_TIMEOUT_S)`** — always
  returns `False`: aider has no resumable session to compact (each turn is a fresh `--message`), so
  the resilience ladder reframes on overflow instead.

### `_aider_effort`

- code: `workhorse/workhorse/runner/backends.py::_aider_effort`

`_aider_effort(effort: str) -> str` clamps the Claude-superset reasoning-effort levels to what
aider's `--reasoning-effort` accepts: aider tops out at `"high"`, so `"xhigh"`/`"max"` map to
`"high"`; every other value (`"low"`/`"medium"`/`"high"`) passes through unchanged.

## Related pieces

- [`_run_text_turn`](run-text-turn.md) — the plain-text turn runner `run_turn` delegates to; owns
  the process spawn, live-echo accumulation, and hand-off to [`_finalize_turn`](finalize-turn.md).
- [`get_backend`](get-backend.md) — resolves `"aider"` to a cached `AiderBackend()` instance.

