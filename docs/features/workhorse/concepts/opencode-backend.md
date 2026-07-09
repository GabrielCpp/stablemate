---
type: concept
slug: opencode-backend
title: OpenCodeBackend — the opencode harness
---
# OpenCodeBackend — the opencode harness

The [AgentBackend](agent-backend.md) implementation for the OpenCode CLI (`opencode run --format
json`) — one of the three JSONL-speaking backends alongside [CodexBackend](codex-backend.md) and
[CopilotBackend](copilot-backend.md). Selected when [run](../workhorse.md#run)'s `--cli` (via
[get_backend](get-backend.md)) resolves to `opencode`. OpenCode speaks plain chat-completions to
whatever provider its model names, so it drives OpenRouter models directly (e.g.
`openrouter/xiaomi/mimo-v2.5`) with **no proxy** — the same OpenRouter-native role
[AiderBackend](aider-backend.md) plays. The prompt is passed as a positional argv message (not
stdin); sessions resume by id via `--session`; it has no in-place compaction. `run_turn` streams the
CLI's event log through [`_opencode_on_event`](opencode-on-event.md), the vocabulary callback that
turns OpenCode's own NDJSON events into the turn's result text and session id, and on a
spending-cap hit probes [`_codex_reset_at`](codex-reset-at.md) for the exact Codex usage-window
reset time.

- code: `workhorse/workhorse/runner/backends.py::OpenCodeBackend`
- extends: [AgentBackend](agent-backend.md)
- verify: `workhorse/tests/test_backends.py::test_opencode_run_turn_fresh_then_resume`,
  `workhorse/tests/test_backends.py::test_opencode_effort_variant_mapping_and_omit`,
  `workhorse/tests/test_backends.py::test_opencode_cap_attaches_codex_reset_at`,
  `workhorse/tests/test_backends.py::test_opencode_non_cap_does_not_probe_codex`,
  `workhorse/tests/test_backends.py::test_non_claude_backends_registered`

## Contract

- `name` = `"opencode"`.
- `default_model` = `None` — the node's `model:` map (or `AGENT_MODEL`) must name a
  provider/model (e.g. `openrouter/...`, `openai/...`); OpenCode has no usable backend default.
- `supports_compaction` = `False`.
- **`run_turn(prompt, node_id, session_id_path, model=None, timeout=DEFAULT_RESULT_TIMEOUT_S,
  cwd=None, add_dirs=None, effort=None)`** — build the argv:
  ```
  opencode --print-logs --log-level ERROR run --format json
           [-m <model>] [--variant <_OPENCODE_VARIANT[effort]>] [--session <sid>]
           -- <prompt>
  ```
  1. Read a persisted session id via [`_read_session_id(session_id_path)`](read-session-id.md)
     (shared with the other JSONL backends).
  2. `--print-logs --log-level ERROR` are always present: they route OpenCode's ERROR-level log
     lines (which carry quota/limit errors, e.g. `"The usage limit has been reached"`) onto stdout
     as non-JSON lines instead of only into `~/.local/share/opencode/log/opencode.log`. Without this
     flag those errors are invisible to the harness, and OpenCode's own internal exponential backoff
     would run silently until the hard watchdog killed the process.
  3. `run --format json` — non-interactive single turn, NDJSON event stream.
  4. `-m <model>` only when the caller named one.
  5. `--variant <variant>` only when `effort` is set **and** maps to a known variant via
     [`_OPENCODE_VARIANT`](#_opencode_variant) — OpenCode's own reasoning-effort knob. `"medium"` has
     no opencode variant, so an `effort="medium"` node omits the flag entirely rather than passing
     something invalid.
  6. If a session id was read, append `--session <sid>` and log
     `[{node_id}] 🔄 Resuming opencode session: {sid[:8]}...`.
  7. `-- <prompt>` — `--` ends option parsing so a prompt beginning with `-` is still read as the
     positional message, never as a flag. `add_dirs` has no OpenCode equivalent and is ignored.
  8. Stream the command through [`_stream_jsonl`](stream-jsonl.md) with
     [`_opencode_on_event`](opencode-on-event.md) as the vocabulary callback and `stdin_data=None`
     (OpenCode reads its message from argv, not stdin), forwarding `cwd` →
     `(state, diagnostics, timed_out, returncode)`.
  9. **Codex-cap reset probe:** if `_agent._is_cap(diagnostics)` is true (this turn hit a spending
     cap), call [`_codex_reset_at(model)`](codex-reset-at.md) to fetch the precise unix-epoch reset
     time and pass it as `rate_reset_at`; otherwise `rate_reset_at=None`. This only ever *sharpens*
     the wait — see [`_codex_reset_at`](codex-reset-at.md)'s own guards (non-`openai/*` models,
     missing OAuth, disabled probe, or any error all yield `None` with no observable effect on a
     non-cap turn).
  10. Return [`_finalize_turn`](finalize-turn.md)`("opencode", node_id, state, diagnostics,
      timed_out, returncode, session_id_path, timeout, rate_reset_at=rate_reset_at)` — raises
      `agent.BackendInvocationError` on failure, carrying `rate_reset_at` through to the runner's
      cap-wait so it sleeps until the actual window reopens instead of a blind default wait.
- **`compact(session_id_path, node_id, model=None, timeout=DEFAULT_RESULT_TIMEOUT_S)`** — always
  returns `False`: OpenCode manages its own context internally (no in-place session compaction), so
  the resilience ladder reframes on context overflow instead.

### `_OPENCODE_VARIANT`

- code: `workhorse/workhorse/runner/backends.py::_OPENCODE_VARIANT`

The effort → OpenCode `--variant` mapping (a plain `dict[str, str]`), since OpenCode's documented
variant levels don't line up one-to-one with the Claude-superset effort vocabulary:

| `effort` | `--variant` |
|---|---|
| `low` | `minimal` |
| `medium` | *(no mapping — flag omitted)* |
| `high` | `high` |
| `xhigh` | `max` |
| `max` | `max` |

## Related pieces

- [`_read_session_id`](read-session-id.md) — reads the persisted `.session_id` file, if any, shared
  by every JSONL backend's `run_turn`.
- [`_stream_jsonl`](stream-jsonl.md) — the shared JSONL event loop `run_turn` streams the `opencode`
  invocation through; owns the process spawn, timeout, and per-line dispatch to `on_event`.
- [`_opencode_on_event`](opencode-on-event.md) — the `on_event` callback that knows OpenCode's own
  NDJSON event vocabulary (`text`/`error`/other, keyed by `sessionID`) and populates
  `state`/`diagnostics`.
- [`_finalize_turn`](finalize-turn.md) — the shared classifier `run_turn` hands the finished stream
  (plus the optional `rate_reset_at`) to, turning it into the turn's result text or a raised
  `BackendInvocationError`.
- [`_codex_reset_at`](codex-reset-at.md) — the best-effort probe that fetches the ChatGPT/Codex
  OAuth backend's `x-codex-primary-reset-at` header for an `openai/*` model, so a Codex usage cap
  hit through OpenCode is waited out until its exact reset instead of a flat default.
- [`get_backend`](get-backend.md) — resolves `"opencode"` to a cached `OpenCodeBackend()` instance.
- [`CodexBackend`](codex-backend.md) / [`CopilotBackend`](copilot-backend.md) — the other two JSONL
  backends sharing `_stream_jsonl`/`_finalize_turn`; [`AiderBackend`](aider-backend.md) is the
  plain-text sibling and the other OpenRouter-native backend.
