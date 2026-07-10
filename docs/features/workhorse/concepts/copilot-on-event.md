---
type: concept
slug: copilot-on-event
title: _copilot_on_event — the Copilot event-vocabulary adapter
---
# _copilot_on_event — the Copilot event-vocabulary adapter

The `on_event` callback [`CopilotBackend.run_turn`](copilot-backend.md) hands to
[`_stream_jsonl`](stream-jsonl.md): it knows `copilot -p --output-format json`'s own event
vocabulary (`assistant.message`, `result`, error events) and is the only piece of the shared JSONL
loop that does — `_stream_jsonl` itself is vocabulary-agnostic and just calls `on_event(event,
state, node_id, diagnostics)` once per parsed line. Its sibling adapters for the other JSONL
backends are [`_codex_on_event`](codex-on-event.md) and
[`_opencode_on_event`](opencode-on-event.md).

- code: `workhorse/workhorse/runner/backends.py::_copilot_on_event`
- extends: [_stream_jsonl](stream-jsonl.md#contract)

## Contract

- **Input:** `(event: dict, state: dict, node_id: str, diagnostics: list)`, matching
  [`_stream_jsonl`](stream-jsonl.md#contract)'s `on_event` calling convention exactly:
  - `event` — one parsed JSON object from a `copilot -p --output-format json` line.
  - `state` — the turn's accumulator, starting as `{"result_text": "", "session_id": None}`;
    mutated in place.
  - `node_id` — the workflow node id, used only for the live-echo log-line prefix.
  - `diagnostics` — the turn's diagnostics list; mutated in place (appended to, never read).
- **Output:** `None` — all effects are the in-place mutations to `state`/`diagnostics` below.
- **Raises:** nothing — a malformed `event`/`data` shape is read defensively (`.get(...)` with
  falsy defaults), never indexed directly.

## Algorithm

Dispatches on `event.get("type") or ""` (`etype`):

1. **`etype == "assistant.message"`** → read `content = (event.get("data") or {}).get("content") or
   ""`; if non-empty, set `state["result_text"] = content` (last non-empty message wins — a turn
   with multiple `assistant.message` events keeps only the final content) and echo
   `[{node_id}] {content.strip()[:500]}` to stdout (live progress, truncated to 500 chars).
2. **`etype == "result"`** → the terminal event of the turn:
   - if `event.get("sessionId")` is truthy, set `state["session_id"] = event["sessionId"]` — the
     resumable session handle used as `sid` in a later turn's `copilot ... --session-id <sid>`.
   - read `exit_code = event.get("exitCode")`; if it is neither `0` nor `None` (a real non-zero
     exit), append `f"copilot exitCode={exit_code}"` to `diagnostics`.
3. **`"error" in etype`** (any other event type containing `"error"`, e.g. a copilot error event) →
   append `json.dumps(event)[:500]` to `diagnostics` — the catch-all for copilot's own error event
   types that aren't carried on `result`.
4. Every other `etype` (e.g. tool-call/progress events copilot may emit) is silently ignored —
   `_copilot_on_event` only extracts the final answer text, the resume id, the exit code, and error
   signals; it does not track turn progress beyond the live echo above.

Both `diagnostics` appends feed [`_stream_jsonl`](stream-jsonl.md#cap-abort-early-exit-on-a-spending-capusage-limit)'s
per-line cap-abort scan (run by its caller immediately after `on_event` returns) and, at the end of
the stream, [`_finalize_turn`](finalize-turn.md)'s classification — a copilot cap or context-overflow
marker surfaces through whichever of these two branches captures the event carrying it, same as a
raw non-JSON diagnostic line.

## Related pieces

- [`_stream_jsonl`](stream-jsonl.md) — the generic event loop that calls this once per parsed JSON
  line and owns everything vocabulary-agnostic (spawn, timeout, cap-abort scan); `_copilot_on_event`
  supplies only the copilot-specific dispatch above.
- [`CopilotBackend`](copilot-backend.md) — the sole caller, passing `_copilot_on_event` to
  `_stream_jsonl(cmd, node_id, timeout, None, _copilot_on_event, cwd=cwd)` in `run_turn` (`None`
  stdin, since Copilot takes its prompt as a `-p` arg rather than on stdin).
- [`_finalize_turn`](finalize-turn.md) — reads `state["result_text"]`/`state["session_id"]` (as
  populated here) and the joined `diagnostics` to classify the turn once the stream ends.
- [`_codex_on_event`](codex-on-event.md) / [`_opencode_on_event`](opencode-on-event.md) — the
  analogous `on_event` adapters for the other two JSONL backends; each parses a different CLI's
  event shape into the same `state`/`diagnostics` contract.
