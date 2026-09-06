---
type: concept
slug: copilot-on-event
title: copilot _on_event — the Copilot event-vocabulary adapter
---
# `_on_event` (copilot) — the Copilot event-vocabulary adapter

The `on_event` callback [`CopilotBackend.run_turn`](copilot-backend.md) hands to
[`stream_jsonl`](stream-jsonl.md): it knows `copilot -p --output-format json`'s own event
vocabulary (`assistant.message`, `result`, error events) and is the only piece of the shared JSONL
loop that does — `stream_jsonl` itself is vocabulary-agnostic and just calls
`on_event(event, state, node_id)` once per parsed line. Its sibling adapters for the other JSONL
backends are [codex's `_on_event`](codex-on-event.md), [cline's `_on_event`](cline-on-event.md)
and [`_OpenCodeEvents.on_event`](opencode-on-event.md).

The name is unqualified: each adapter module owns exactly one `_on_event`, because module scope
already supplies the disambiguation a `_copilot_` prefix used to.

- code: `workhorse/workhorse/runner/backends/copilot.py::_on_event`
- extends: [stream_jsonl](stream-jsonl.md#contract)
- tests: `workhorse/tests/test_backends.py::test_copilot_on_event_extracts_text_and_session`

## Contract

- **Input:** `(event: dict, state: TurnState, node_id: str)` — **three arguments**, matching
  [`stream_jsonl`](stream-jsonl.md#contract)'s calling convention exactly:
  - `event` — one parsed JSON object from a `copilot -p --output-format json` line.
  - `state` — the turn's [`TurnState`](finalize-turn.md#turnstate), mutated in place. Diagnostics
    go on `state.diagnostics`; there is no separate list argument.
  - `node_id` — the workflow node id, used only for the live-echo log-line prefix.
- **Output:** `None` — all effects are the in-place mutations to `state` below.

## Algorithm

Dispatches on `event.get("type") or ""` (`etype`):

Copilot uses `result` for its turn summary, but its usage payload has not been verified against a
live run. That uncertainty is why the adapter delegates usage interpretation to the shared
tolerant [normalization](finalize-turn.md#turnstate) instead of defining a backend-specific
payload.

1. **`etype == "assistant.message"`** → read `content = (event.get("data") or {}).get("content") or
   ""`; if non-empty, set `state.result_text = content` (last non-empty message wins — a turn with
   multiple `assistant.message` events keeps only the final content) and echo
   `[{node_id}] {content.strip()[:500]}` to stdout (live progress, truncated to 500 chars).
2. **`etype == "result"`** → read three values from the event:
   - if `event.get("sessionId")` is truthy, set `state.session_id = event["sessionId"]` — the
     resumable session handle used as `sid` in a later turn's `copilot ... --session-id <sid>`.
   - `state.usage = state.usage.merge(usage.normalize(event))` — the turn's token/cost report.
   - read `exit_code = event.get("exitCode")`; if it is neither `0` nor `None` (a real non-zero
     exit), append `f"copilot exitCode={exit_code}"` to `state.diagnostics`.
3. **`"error" in etype`** (any other event type containing `"error"`) → append
   `json.dumps(event)[:500]` to `state.diagnostics` — the catch-all for copilot's own error event
   types that aren't carried on `result`.
4. Every other `etype` (e.g. tool-call/progress events copilot may emit) is silently ignored —
   this adapter extracts the final answer text, the resume id, the usage, the exit code, and error
   signals; it does not track turn progress beyond the live echo above.

Both `diagnostics` appends feed
[`stream_jsonl`](stream-jsonl.md#early-abort)'s per-line early-abort
scan (run by its caller immediately after `on_event` returns) and, at the end of the stream,
[`finalize_turn`](finalize-turn.md)'s classification — a copilot cap or context-overflow marker
surfaces through whichever of these two branches captures the event carrying it, same as a raw
non-JSON diagnostic line.

## Related pieces

- [`stream_jsonl`](stream-jsonl.md) — the generic event loop that calls this once per parsed JSON
  line and owns everything vocabulary-agnostic (spawn, timeout, early-abort scan); this adapter
  supplies only the copilot-specific dispatch above.
- [`CopilotBackend`](copilot-backend.md) — the sole caller, passing `_on_event` to
  `stream_jsonl(cmd, node_id, timeout, None, _on_event, resilience=resilience, cwd=cwd,
  env_extra=self.harness_env())` in `run_turn` (`None` stdin, since Copilot takes its prompt as a
  `-p` arg rather than on stdin).
- [`TurnState`](finalize-turn.md#turnstate) — the struct this mutates; the same one every backend
  fills, which is why one classifier can read all of them.
- [`finalize_turn`](finalize-turn.md) — reads the `result_text`/`session_id`/`usage` populated here
  and the joined diagnostics to classify the turn once the stream ends.
- [codex's `_on_event`](codex-on-event.md) / [cline's `_on_event`](cline-on-event.md) /
  [`_OpenCodeEvents.on_event`](opencode-on-event.md) —
  the analogous adapters for the other three JSONL backends; each parses a different CLI's event
  shape into the same `TurnState`.
