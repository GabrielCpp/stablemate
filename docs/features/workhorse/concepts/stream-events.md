---
type: concept
slug: stream-events
title: _stream_events — parsing the Claude stream-json line stream
---
# `_stream_events` — parsing the Claude stream-json line stream

Turns `claude --output-format stream-json`'s raw line stream into the
[`ClaudeTurnStream`](#claudeturnstream) that [`_run_cli`](run-claude-cli.md#algorithm) reads. It
delegates the spawn/timeout/kill mechanics to [`stream_subprocess`](stream-subprocess.md), passing
it a per-line closure (`on_line`) that both accumulates turn state and echoes a concise live view
via [`_emit_event`](emit-event.md).

Unlike the Codex/Copilot/OpenCode backends — which split the generic event loop
([`stream_jsonl`](stream-jsonl.md)) from a CLI-specific vocabulary adapter
([codex's `_on_event`](codex-on-event.md) and siblings) — `_stream_events` fuses both roles into
one function and calls [`stream_subprocess`](stream-subprocess.md) directly. Claude is the only
backend with this protocol shape, so there is no second caller to share the split with, and the
struct it fills is its own rather than the shared [`TurnState`](finalize-turn.md#turnstate).

- code: `workhorse/workhorse/runner/backends/claude.py::_stream_events`
- extends: [stream_subprocess](stream-subprocess.md#contract)

## `ClaudeTurnStream`

- code: `workhorse/workhorse/runner/backends/claude.py::ClaudeTurnStream`

A `@dataclass(slots=True)` holding what one Claude turn yielded as its stream went past. Mutable by
construction: the per-line callback writes into it event by event, and the process outcome lands on
it once the stream closes. It replaces a seven-element tuple every caller had to decode by counting
positions.

| Field | Default | Meaning |
|---|---|---|
| `result_text: str` | `""` | the last non-empty `result` event's `result` field |
| `session_id: str \| None` | `None` | the most recent `system` event's `session_id` |
| `diagnostics: list[str]` | `[]` | anything signalling *how* a turn failed — non-event output lines (e.g. "Spending cap reached") and error-result subtypes |
| `timed_out: bool` | `False` | `stream_subprocess`'s own flag, passed through unchanged |
| `rate_limited: bool` | `False` | `True` once any `rate_limit_event` reported the limit as hit |
| `rate_reset_at: float \| None` | `None` | the most recent window-reset epoch seen; used only if the failure is otherwise a cap |
| `returncode: int` | `0` | the child's exit code |

`diagnostics_text` is a read-only property returning `"\n".join(self.diagnostics)` — the single
string [`classify_turn`](classify-turn.md#ladder-first-match-wins) scans.

This is deliberately **not** the shared [`TurnState`](finalize-turn.md#turnstate) the four JSONL
backends fill. Those go through [`finalize_turn`](finalize-turn.md), which reads `TurnState`
and calls `classify_turn` on their behalf; Claude calls `classify_turn` itself, so it needs an
accumulator shaped for that call rather than for the shared one.

## Contract

- **Input:**
  - `cmd: list[str]` — the `claude` argv built by [`_run_cli`](run-claude-cli.md#algorithm).
  - `node_id: str` — used for the live-echo log-line prefix (`[{node_id}] …`) and forwarded to
    [`stream_subprocess`](stream-subprocess.md) for its own logging and `WORKHORSE_NODE_ID` export.
  - `timeout: float` — forwarded straight through to `stream_subprocess`'s in-loop check and
    watchdog; this function performs no timeout logic of its own.
  - `resilience: AgentResilience` (**keyword-only, required**) — forwarded verbatim to
    `stream_subprocess` for the watchdog grace, the heartbeat interval and the exec-retry budget.
  - `stdin_data: str | None` (keyword, default `None`) — the rendered prompt, piped to the child's
    stdin (`-p` prompt-from-stdin mode).
  - `cwd: str | None` (keyword, default `None`) — subprocess working directory.
  - `env_extra: dict[str, str] | None` (keyword, default `None`) — the `[harness.claude].env`
    table, layered over the inherited environment inside `stream_subprocess`.
- **Output:** a [`ClaudeTurnStream`](#claudeturnstream), fully populated.
- **Raises:** nothing turn-specific — a malformed line is caught (`json.JSONDecodeError`) and
  folded into `diagnostics` rather than propagated. A permanently-missing or un-exec'able CLI
  surfaces as the `BackendInvocationError`
  [`_spawn_streaming`](stream-subprocess.md#_spawn_streaming) raises, never a bare `OSError`.

## Algorithm

1. **Construct the accumulator:** `stream = ClaudeTurnStream()`, closed over and mutated by the
   nested `on_line`.
2. **Define `on_line(raw_line: str) -> None`**, the per-line callback:
   - Strip the line; a blank line is a no-op.
   - Parse it as JSON. **On `JSONDecodeError`** (e.g. merged stderr text, a non-JSON banner line):
     print `[{node_id}] {line}` for live visibility and append the raw line to
     `stream.diagnostics`, then return — this is the only path a non-JSON line takes.
   - Dispatch on the parsed event's `type` (`etype`):
     - **`"result"`** — set `stream.result_text = event.get("result", "") or stream.result_text`
       (a falsy/missing `result` field keeps the prior value rather than clobbering it to empty).
       Then call [`otel.turn_result`](#telemetry)`(usage.normalize(event))` — **unconditionally**.
       If `event.get("is_error")` is truthy, or `event.get("subtype")` is neither `None` nor
       `"success"`, append `f"{subtype} {result}"` to `stream.diagnostics` — an error result
       carries its reason in `subtype`/`result`, and this is how that reason reaches
       [`classify_turn`](classify-turn.md#ladder-first-match-wins).
     - **`"rate_limit_event"`** — call
       [`rate_limit_info`](classify-turn.md#rate_limit_info)`(event)` → `(blocked, reset_at)`. If
       `reset_at is not None`, overwrite `stream.rate_reset_at` (last-seen window wins, used only
       if the turn is later classified as a cap). If `blocked`, set `stream.rate_limited = True`
       (sticky — once `True`, later non-blocked events don't clear it).
     - **`"system"` with a `"session_id"` key present** — set
       `stream.session_id = event["session_id"]`.
     - any other `etype` — no state update, but still falls through to the next step.
   - **Every successfully-parsed event**, regardless of type, is passed to
     [`_emit_event`](emit-event.md)`(node_id, event)` for the live-progress echo.
3. **Stream the turn:** `stream.timed_out, stream.returncode = stream_subprocess(cmd, node_id,
   timeout, on_line, resilience=resilience, stdin_data=stdin_data, cwd=cwd,
   env_extra=env_extra)` — this is the only place spawn/timeout/kill happens. `on_line` returns
   `None`, never a truthy early-abort signal, so a run only ends early via `stream_subprocess`'s
   own in-loop/watchdog timeout, never via a line-content trigger.
4. **Return** the populated `stream`.

## Telemetry

The `result` branch calls `otel.turn_result(usage.normalize(event))` on **every** result event, not
only when the event reports tokens. Claude's result event carries `duration_ms` even when its token
counts are absent, and per-node latency attribution is worth the same call. Normalization goes
through [the same mapper every other backend uses](finalize-turn.md#turnstate), so one query shape
reads them all.

This is the one place Claude's path differs from [`finalize_turn`](finalize-turn.md), which guards
the same call on a non-empty usage — there, an absent usage means the backend reported nothing at
all, and an empty span attribute would be indistinguishable from a real zero.

## Cap detection differs from the JSONL backends

[`stream_jsonl`](stream-jsonl.md) (Codex/Copilot/OpenCode) scans each line for a cap marker and
returns `True` from its `on_line` to trigger
[`stream_subprocess`'s early-abort contract](stream-subprocess.md#contract), ending the turn the
instant a cap is detected. `_stream_events`'s `on_line` never does this — a Claude cap surfaces
only as an error-`result` event's `subtype`/`result` text (folded into `diagnostics` per step 2
above) or a blocked `rate_limit_event`, and is recognized after the stream ends, when
[`classify_turn`](classify-turn.md#ladder-first-match-wins) inspects the accumulated
`diagnostics_text` / `rate_limited` / `rate_reset_at`. A Claude turn that hits a spending cap
therefore still runs to whatever natural end the CLI gives it (its own `result` event or EOF)
rather than being killed mid-stream.

## Related pieces

- [`_run_cli`](run-claude-cli.md#algorithm) — the sole caller; reads this function's returned
  struct field by field into its `classify_turn` call.
- [`stream_subprocess`](stream-subprocess.md) — owns the actual process spawn, line delivery, dual
  timeout, and process-group kill; this function only interprets the lines it's handed.
- [`classify_turn`](classify-turn.md#ladder-first-match-wins) — the consumer of this function's
  output; turns `diagnostics_text`/`timed_out`/`rate_limited`/`rate_reset_at` into either the
  returned result text or a classified `BackendInvocationError`.
- [`rate_limit_info`](classify-turn.md#rate_limit_info) — reads a `rate_limit_event` into
  `(blocked, reset_at)`; called once per such event inside `on_line`.
- [`_emit_event`](emit-event.md) — the live-echo printer called once per successfully-parsed
  event, independent of the state accumulation above.
- [`stream_jsonl`](stream-jsonl.md) / [codex's `_on_event`](codex-on-event.md) — the
  generic-loop-plus-vocabulary-adapter split the four JSONL backends use instead of this
  function's fused approach; see
  [Cap detection](#cap-detection-differs-from-the-jsonl-backends) for the resulting behavioral
  difference.
- [`TurnState`](finalize-turn.md#turnstate) — the shared accumulator those backends fill, and the
  struct [`ClaudeTurnStream`](#claudeturnstream) deliberately is not.
