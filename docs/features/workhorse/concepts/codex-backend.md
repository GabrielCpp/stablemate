---
type: concept
slug: codex-backend
title: CodexBackend — the codex harness
---
# CodexBackend

The [AgentBackend](agent-backend.md) implementation for OpenAI's `codex` CLI. Selected when
[run](../workhorse.md#run)'s `--cli` (via [get_backend](get-backend.md)) resolves to `codex`.

- extends: [AgentBackend](agent-backend.md)
- code: `workhorse/workhorse/runner/backends.py::CodexBackend`

## Contract

- `name` = `"codex"`.
- **`run_turn`** — invoke `codex exec --json`, streaming its event log; the turn's result is the
  text of the terminal `item.completed` event (bracketed by `thread.started`). Raise
  `BackendInvocationError` if no result event arrives.
- **Model / profile mapping** — the configured `power`→model value selects a codex config profile
  plus an optional model override, written `<profile>[@<model-slug>]` (`@` is the delimiter since
  `/` and `:` appear in slugs): `local` → `--profile local`; `openrouter@deepseek/x` → `--profile
  openrouter -m deepseek/x`; `@gpt-5.5` → `-m gpt-5.5`; unset → `CODEX_PROFILE` or the codex
  default.
- **`compact`** — codex has no in-place compaction; returns `False` (caller reframes on overflow).
- **`effort`** — translated to codex's `model_reasoning_effort`.
