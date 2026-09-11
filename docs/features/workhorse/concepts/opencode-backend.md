---
type: concept
slug: opencode-backend
title: OpenCodeBackend — the opencode harness
---
# OpenCodeBackend — the opencode harness

The [AgentBackend](agent-backend.md) implementation for the OpenCode CLI (`opencode run --format
json`) — one of the four JSONL-speaking backends alongside [CodexBackend](codex-backend.md),
[CopilotBackend](copilot-backend.md) and [ClineBackend](cline-backend.md). Selected when
[run](../workhorse.md#run)'s `--cli` (via
[get_backend](get-backend.md)) resolves to `opencode`. OpenCode speaks plain chat-completions to
whatever provider its model names, so it drives OpenRouter models directly (e.g.
`openrouter/example-org/example-model`) with **no proxy** — the same OpenRouter-native role
[ClineBackend](cline-backend.md) plays. The prompt is passed as a positional argv message (not
stdin); sessions resume by id via `--session`; it has no in-place compaction. `run_turn` streams
the CLI's event log through [`_OpenCodeEvents.on_event`](opencode-on-event.md), the vocabulary
reader that turns OpenCode's own NDJSON events into the turn's result text, session id and usage,
and on a spending-cap hit probes [`_codex_reset_at`](codex-reset-at.md) for the exact Codex
usage-window reset time.

Class, event reader and cap probe all live in `runner/backends/opencode.py` — one module per CLI,
so importing [the port](agent-backend.md) drags in no adapter.

- code: `workhorse/workhorse/runner/backends/opencode.py::OpenCodeBackend`
- extends: [AgentBackend](agent-backend.md)
- tests: `workhorse/tests/test_backends.py::test_opencode_run_turn_fresh_then_resume`,
  `workhorse/tests/test_backends.py::test_opencode_attaches_a_large_prompt_instead_of_putting_it_in_argv`,
  `workhorse/tests/test_backends.py::test_opencode_effort_variant_mapping_and_omit`,
  `workhorse/tests/test_backends.py::test_opencode_pins_small_model_to_turn_model`,
  `workhorse/tests/test_backends.py::test_opencode_no_model_no_small_model_pin`,
  `workhorse/tests/test_backends.py::test_opencode_operator_config_content_wins_verbatim`,
  `workhorse/tests/test_backends.py::test_opencode_pin_composes_with_other_harness_env`,
  `workhorse/tests/test_backends.py::test_opencode_lifts_the_32k_output_cap_to_the_models_own_limit`,
  `workhorse/tests/test_backends.py::test_opencode_operator_output_cap_wins`,
  `workhorse/tests/test_backends.py::test_opencode_cap_attaches_codex_reset_at`,
  `workhorse/tests/test_backends.py::test_opencode_non_cap_does_not_probe_codex`,
  `workhorse/tests/test_backends.py::test_non_claude_backends_registered`

## Contract

- `name` = `"opencode"`.
- `default_model` = `None` — the node (or `AGENT_MODEL`) must name a provider/model (e.g.
  `openrouter/...`, `openai/...`); OpenCode has no usable backend default.
- `supports_compaction` = `False`.
**`run_turn(prompt, node_id, session_id_path, model=None, *, timeout, resilience, cwd=None,
  add_dirs=None, effort=None)`** — `timeout` and `resilience` are keyword-only and required
  ([why](agent-backend.md#run_turn-abstract)). Builds the argv:
  ```
  opencode --print-logs --log-level ERROR run --format json --thinking
           [-m <model>] [--variant <_OPENCODE_VARIANT[effort]>] [--session <sid>]
           [--file <attachment>] -- <prompt>
  ```
   1. Read a persisted session id via [`read_session_id(session_id_path)`](read-session-id.md)
      (shared with the other JSONL backends).
   2. Compute `argv_prompt, attachment = prepare_argv_prompt(prompt, prompt_path)` — a prompt
      within the per-argument byte cap stays as `argv_prompt`; an oversized prompt (or one the
      caller supplied via `prompt_path`) is staged to that file and `argv_prompt` becomes a
      one-line pointer telling the model to read the attached file. The `attachment` returned
      alongside it is the path the later `--file` step attaches.
   3. `--print-logs --log-level ERROR` route OpenCode's ERROR-level log
      lines (which carry quota/limit errors, e.g. `"The usage limit has been reached"`) onto stdout
      as non-JSON lines instead of only into `~/.local/share/opencode/log/opencode.log`. Without
      these flags those errors are invisible to the harness, and OpenCode's own internal exponential
      backoff would run silently until the hard watchdog killed the process. They are what makes
      [`stream_jsonl`'s early abort](stream-jsonl.md#early-abort)
      possible on this backend at all.
   4. `run --format json` — non-interactive single turn, NDJSON event stream.
   5. `--thinking` is always passed so OpenCode's reasoning events reach the stream.
   6. `-m <model>` only when the caller named one.
   7. `--variant <variant>` only when `effort` is set **and** maps to a known variant via
      [`_OPENCODE_VARIANT`](#_opencode_variant) — OpenCode's own reasoning-effort knob. `"medium"`
      has no opencode variant, so an `effort="medium"` node omits the flag entirely rather than
      passing something invalid.
   8. If a session id was read, append `--session <sid>` and log
      `[{node_id}] 🔄 Resuming opencode session: {sid[:8]}...`.
   9. `--file <attachment>` only when step 2 spilled the prompt to a file — otherwise the flag is
      absent and `argv_prompt` carries the message directly.
   10. `-- <argv_prompt>` — `--` ends option parsing so a prompt beginning with `-` is still read as
       the positional message (or the path of the attached file step 9 named), never as a flag.
       `add_dirs` has no OpenCode equivalent and is ignored.
   11. **Harness env composition:** `env_extra` starts from `self.harness_env()` and is augmented
       before the stream is invoked. When the caller named a model and `OPENCODE_CONFIG_CONTENT`
       is not already in `env_extra`, it is set to `{"small_model": <model>}` — opencode's
       internal title/summary helper has no CLI flag, reads `small_model` from config, and without
       the pin it inherits whatever provider the machine's `opencode.jsonc` names, so a helper
       routed at a provider the run doesn't otherwise use (an OpenRouter credit wall on the
       title call) classified as a cap on the node and slept a run for 6 days while its coding
       models were fine. And when `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` is not already in
       `env_extra`, it is set to `"131072"` — opencode caps every completion at 32 000 output
       tokens (thinking included) by default, the only override is this env var (opencode reads
       it as `Math.min(model.limit.output, value)`, so a large value is safe on every model), and
       a reasoning model handed a 34k-token review packet otherwise spends all 32k thinking and
       ends with `reason: length` and no text part. An operator who names either variable in
       `[harness.opencode].env` has decided; the augmentation steps aside verbatim.
   12. Stream the command through [`stream_jsonl`](stream-jsonl.md#contract) with a **fresh**
       `_OpenCodeEvents().on_event` as the vocabulary callback and `stdin_data=None` (OpenCode reads
       its message from argv, not stdin), forwarding `resilience=resilience`, `cwd=cwd` and
       `env_extra=env_extra` → a [`TurnState`](finalize-turn.md#turnstate). One instance per
       turn is what keeps the reader's accumulated text parts from leaking into the next turn
       (`test_opencode_text_parts_do_not_leak_between_turns`).
   13. **Codex-cap reset probe:** if [`failure.is_cap(state.diagnostics_text)`](classify-turn.md#is_cap)
       is true (this turn hit a spending cap), call [`_codex_reset_at(model)`](codex-reset-at.md) to
       fetch the precise unix-epoch reset time and pass it as `rate_reset_at`; otherwise
       `rate_reset_at=None`. This only ever *sharpens* the wait — see
       [`_codex_reset_at`](codex-reset-at.md)'s own guards (non-`openai/*` models, missing OAuth,
       disabled probe, or any error all yield `None` with no observable effect on a non-cap turn).
   14. Return [`finalize_turn`](finalize-turn.md)`("opencode", node_id, state, session_id_path,
       timeout, rate_reset_at=rate_reset_at)` — raises
       [`BackendInvocationError`](classify-turn.md#backendinvocationerror) on failure, carrying
       `rate_reset_at` through to the runner's [cap wait](cap-delay-seconds.md) so it sleeps until
        the actual window reopens instead of a blind default wait.
- consistency: opencode-command — every OpenCode `run_turn` command includes `--print-logs --log-level ERROR` before
  `run`, so quota and limit errors are available to the harness as diagnostics
- **`compact(session_id_path, node_id, model=None, *, timeout, resilience)`** — always returns
  `False`: OpenCode manages its own context internally (no in-place session compaction), so the
  resilience ladder reframes on context overflow instead.

### `_OPENCODE_VARIANT`

- code: `workhorse/workhorse/runner/backends/opencode.py::_OPENCODE_VARIANT`

The effort → OpenCode `--variant` mapping (a plain `dict[str, str]`), since OpenCode's documented
variant levels don't line up one-to-one with the Claude-superset effort vocabulary:

| `effort` | `--variant` |
|---|---|
| `low` | `minimal` |
| `medium` | *(no mapping — flag omitted)* |
| `high` | `high` |
| `xhigh` | `max` |
| `max` | `max` |

## Methods

### run_turn
- sig: `run_turn(prompt: str, node_id: str, session_id_path: Path | None, model: str | None = None, *, prompt_path: Path | None = None, timeout: float, resilience: AgentResilience, cwd: str | None = None, add_dirs: list[str] | None = None, effort: str | None = None) -> str`
- does: runs OpenCode's JSON stream, optionally resumes a session, pins its small model when needed, and probes a Codex-provider cap reset
- raises: `BackendInvocationError` after `finalize_turn` classifies the streamed state
- verify: emitted(event="OpenCode turn result", count=1)
- code: `workhorse/workhorse/runner/backends/opencode.py::OpenCodeBackend.run_turn`

### compact
- sig: `compact(session_id_path: Path | None, node_id: str, model: str | None = None, *, timeout: float, resilience: AgentResilience) -> bool`
- does: declines in-place session compaction
- returns: `false`
- verify: json_path(path="$.compacted", equals=false)
- code: `workhorse/workhorse/runner/backends/opencode.py::OpenCodeBackend.compact`

## Related pieces

- [`read_session_id`](read-session-id.md) — reads the persisted `.session_id` file, if any, shared
  by every JSONL backend's `run_turn`.
- [`stream_jsonl`](stream-jsonl.md) — the shared JSONL event loop `run_turn` streams the `opencode`
  invocation through; owns the process spawn, timeout, per-line dispatch, and the early-abort scan
  that OpenCode's `--print-logs` lines feed.
- [`_OpenCodeEvents.on_event`](opencode-on-event.md) — the per-turn event reader that knows
  OpenCode's own NDJSON vocabulary (`text`/`step_finish`/`error`, keyed by `sessionID`) and
  populates the [`TurnState`](finalize-turn.md#turnstate).
- [`finalize_turn`](finalize-turn.md) — the shared classifier `run_turn` hands the finished
  `TurnState` (plus the optional `rate_reset_at`) to, turning it into the turn's result text or a
  raised `BackendInvocationError`.
- [`_codex_reset_at`](codex-reset-at.md) — the best-effort probe that fetches the ChatGPT/Codex
  OAuth backend's `x-codex-primary-reset-at` header for an `openai/*` model, so a Codex usage cap
  hit through OpenCode is waited out until its exact reset instead of a flat default.
- [`get_backend`](get-backend.md) — resolves `"opencode"` to a cached `OpenCodeBackend()` instance.
- [`CodexBackend`](codex-backend.md) / [`CopilotBackend`](copilot-backend.md) /
  [`ClineBackend`](cline-backend.md) — the other three JSONL backends sharing
  `stream_jsonl`/`finalize_turn`; cline is the other OpenRouter-native backend.
