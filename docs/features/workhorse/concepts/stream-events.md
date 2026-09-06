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
- consistency: claude-turn-stream.diagnostics — A non-empty malformed stream line is retained in `ClaudeTurnStream.diagnostics`
  after `json.JSONDecodeError`, rather than propagating the decoding error.
- verify: json_path(path="$.diagnostics[0]", equals="not-json")

Permanent CLI startup failures remain the `BackendInvocationError` raised by
[`ProcessSupervisor.spawn`](stream-subprocess.md#processsupervisorspawn), rather than bare `OSError` values
from the launcher.

## Algorithm

1. **Construct the accumulator:** `stream = ClaudeTurnStream()`, closed over and mutated by the
   nested `on_line`.
2. **Handle each delivered line:** processing follows the branches described below.

The nested `on_line(raw_line: str) -> None` callback strips the line first, with a blank line
producing no further work. It then parses the content as JSON. A `JSONDecodeError` (for example,
from merged stderr text or a non-JSON banner line) leads to `[{node_id}] {line}` being printed for
live visibility and the raw line being appended to `stream.diagnostics`; processing of that line
then ends. This is the only path taken by a non-JSON line.

For parsed events, the callback dispatches on the event's `type` (`etype`). A `"result"` event
sets `stream.result_text = event.get("result", "") or stream.result_text`, so a falsy or missing
`result` field keeps the prior value rather than clobbering it to empty. It then calls
[`otel.turn_result`](#telemetry)`(usage.normalize(event))` unconditionally. When
`event.get("is_error")` is truthy, or `event.get("subtype")` is neither `None` nor `"success"`, it
appends `f"{subtype} {result}"` to `stream.diagnostics`; this is how an error result's reason
reaches [`classify_turn`](classify-turn.md#ladder-first-match-wins).

A `"rate_limit_event"` goes through
[`rate_limit_info`](classify-turn.md#rate_limit_info)`(event)` to produce `(blocked, reset_at)`.
A non-`None` reset time replaces `stream.rate_reset_at`, making the last-seen window win, and a
blocked result makes `stream.rate_limited` sticky. A `"system"` event with a `"session_id"` key
updates `stream.session_id`; other event types make no state update. Every successfully parsed
event still reaches [`_emit_event`](emit-event.md)`(node_id, event)` for the live-progress echo.
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
