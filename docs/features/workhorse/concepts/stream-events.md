---
type: concept
slug: stream-events
title: _stream_events — parsing the Claude stream-json line stream
---
# _stream_events — parsing the Claude stream-json line stream

The sole caller-facing piece of Claude's protocol code that turns `claude --output-format
stream-json`'s raw line stream into the `(result_text, session_id, diagnostics, timed_out,
rate_limited, rate_reset_at, returncode)` tuple [`_run_claude_cli`](run-claude-cli.md#algorithm)
unpacks. It delegates the actual spawn/timeout/kill mechanics to
[`stream_subprocess`](stream-subprocess.md), passing it a per-line closure (`on_line`) that both
accumulates turn state and echoes a concise live view via [`_emit_event`](emit-event.md).

Unlike the Codex/Copilot/OpenCode backends — which split the generic event loop
([`_stream_jsonl`](stream-jsonl.md)) from a CLI-specific vocabulary adapter
([`_codex_on_event`](codex-on-event.md) and siblings) — `_stream_events` fuses both roles into one
function and calls [`stream_subprocess`](stream-subprocess.md) directly, since Claude is the only
backend with this exact protocol shape and there is no second caller to share the split with.

- code: `workhorse/workhorse/runner/agent.py::_stream_events`
- extends: [stream_subprocess](stream-subprocess.md#contract)

## Contract

- **Input:**
  - `cmd: list[str]` — the `claude` argv built by [`_run_claude_cli`](run-claude-cli.md#algorithm).
  - `node_id: str` — used only for the live-echo log-line prefix (`[{node_id}] …`), forwarded
    to [`stream_subprocess`](stream-subprocess.md) for its own logging/env export.
  - `timeout: float` — forwarded straight through to `stream_subprocess`'s in-loop check and
    watchdog; this function performs no timeout logic of its own.
  - `stdin_data: str | None` (keyword, default `None`) — the rendered prompt, piped to the
    child's stdin (`-p` prompt-from-stdin mode).
  - `cwd: str | None` (keyword, default `None`) — subprocess working directory.
- **Output:** `tuple[str, str | None, str, bool, bool, float | None, int]` —
  `(result_text, session_id, diagnostics, timed_out, rate_limited, rate_reset_at, returncode)`:
  - `result_text` — the last `result` event's `result` field seen (empty string if none arrived).
  - `session_id` — the most recent `system` event's `session_id`, or `None` if no such event
    arrived (a wedged or immediately-killed turn).
  - `diagnostics` — every diagnostic line collected, newline-joined; empty string if none.
  - `timed_out` — `stream_subprocess`'s own `timed_out` flag, passed through unchanged (this
    function never requests an early abort — see [Cap detection](#cap-detection-differs-from-the-jsonl-backends)).
  - `rate_limited` — `True` if any `rate_limit_event` reported the limit as actually hit.
  - `rate_reset_at` — the most recent window-reset epoch seen across all `rate_limit_event`s, or
    `None`; meaningful only when the caller later determines the failure is a cap.
  - `returncode` — the child's exit code, passed through from `stream_subprocess` unchanged.
- **Raises:** nothing turn-specific — a malformed line is caught (`json.JSONDecodeError`) and
  folded into `diagnostics` rather than propagated; a `Popen` failure inside `stream_subprocess`
  still propagates as its normal `OSError`.

## Algorithm

1. **Initialize accumulators:** `st = {"result_text": "", "session_id": None, "rate_reset_at":
   None, "rate_limited": False}` and `diagnostics: list[str] = []`, both closed over and mutated
   by the nested `on_line`.
2. **Define `on_line(raw_line: str) -> None`**, the per-line callback:
   - Strip the line; a blank line is a no-op.
   - Parse it as JSON. **On `JSONDecodeError`** (e.g. merged stderr text, a non-JSON banner line):
     print `[{node_id}] {line}` for live visibility and append the raw line to `diagnostics`, then
     return — this is the only path a non-JSON line takes.
   - Dispatch on the parsed event's `type` (`etype`):
     - **`"result"`** — set `st["result_text"] = event.get("result", "") or st["result_text"]`
       (a falsy/missing `result` field keeps the prior value rather than clobbering it to empty).
       If `event.get("is_error")` is truthy, or `event.get("subtype")` is neither `None` nor
       `"success"`, append `f"{subtype} {result}"` to `diagnostics` — an error result carries its
       reason in `subtype`/`result`, and this is how that reason reaches
       [`classify_turn`](classify-turn.md#ladder-first-match-wins).
     - **`"rate_limit_event"`** — call [`_rate_limit_info`](classify-turn.md#_rate_limit_info)`(event)`
       → `(blocked, reset_at)`. If `reset_at is not None`, overwrite `st["rate_reset_at"]` (last-seen
       window wins, used only if the turn is later classified as a cap). If `blocked`, set
       `st["rate_limited"] = True` (sticky — once `True`, later non-blocked events don't clear it).
     - **`"system"` with a `"session_id"` key present** — set `st["session_id"] = event["session_id"]`.
     - any other `etype` — no state update, but still falls through to the next step.
   - **Every successfully-parsed event**, regardless of type, is passed to
     [`_emit_event`](emit-event.md)`(node_id, event)` for the live-progress echo.
3. **Stream the turn:** `timed_out, returncode = stream_subprocess(cmd, node_id, timeout, on_line,
   stdin_data=stdin_data, cwd=cwd)` — this is the only place spawn/timeout/kill happens; `on_line`
   never returns a truthy early-abort signal (its return type is `None`), so a run only ends early
   via `stream_subprocess`'s own in-loop/watchdog timeout, never via a line-content trigger.
4. **Return** `(st["result_text"], st["session_id"], "\n".join(diagnostics), timed_out,
   st["rate_limited"], st["rate_reset_at"], returncode)`.

## Cap detection differs from the JSONL backends

[`_stream_jsonl`](stream-jsonl.md) (Codex/Copilot/OpenCode) scans each line for a cap marker and
returns `True` from its `on_line` to trigger `stream_subprocess`'s early-abort contract, ending the
turn the instant a cap is detected. `_stream_events`'s `on_line` never does this — a Claude cap
surfaces only as an error-`result` event's `subtype`/`result` text (folded into `diagnostics` per
step 2 above) or a blocked `rate_limit_event`, and is recognized after the stream ends, when
[`classify_turn`](classify-turn.md#ladder-first-match-wins) inspects the accumulated `diagnostics`/
`rate_limited`/`rate_reset_at`. A Claude turn that hits a spending cap therefore still runs to
whatever natural end the CLI gives it (its own `result` event or EOF) rather than being killed
mid-stream.

## Related pieces

- [`_run_claude_cli`](run-claude-cli.md#algorithm) — the sole caller; unpacks this function's
  7-tuple directly into its `classify_turn` call.
- [`stream_subprocess`](stream-subprocess.md) — owns the actual process spawn, line delivery,
  dual timeout, and process-group kill; this function only interprets the lines it's handed.
- [`classify_turn`](classify-turn.md#ladder-first-match-wins) — the consumer of this function's
  output tuple; turns `diagnostics`/`timed_out`/`rate_limited`/`rate_reset_at` into either the
  returned result text or a classified `BackendInvocationError`.
- [`_rate_limit_info`](classify-turn.md#_rate_limit_info) — reads a `rate_limit_event` into
  `(blocked, reset_at)`; called once per such event inside `on_line`.
- [`_emit_event`](emit-event.md) — the live-echo printer called once per successfully-parsed
  event, independent of the state accumulation above.
- [`_stream_jsonl`](stream-jsonl.md) / [`_codex_on_event`](codex-on-event.md) — the
  generic-loop-plus-vocabulary-adapter split the other three backends use instead of this
  function's fused approach; see [Cap detection](#cap-detection-differs-from-the-jsonl-backends)
  for the resulting behavioral difference.
