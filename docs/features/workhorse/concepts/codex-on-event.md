---
type: concept
slug: codex-on-event
title: _codex_on_event — the Codex event-vocabulary adapter
---
# _codex_on_event — the Codex event-vocabulary adapter

The `on_event` callback [`CodexBackend.run_turn`](codex-backend.md) hands to
[`_stream_jsonl`](stream-jsonl.md): it knows `codex exec --json`'s own event vocabulary (`thread.started`,
`item.completed`, error/fail events) and is the only piece of the shared JSONL loop that does — `_stream_jsonl`
itself is vocabulary-agnostic and just calls `on_event(event, state, node_id, diagnostics)` once per parsed
line. Its sibling adapters for the other JSONL backends are [`_copilot_on_event`](copilot-on-event.md) and
[`_opencode_on_event`](opencode-on-event.md).

- code: `workhorse/workhorse/runner/backends.py::_codex_on_event`
- extends: [_stream_jsonl](stream-jsonl.md#contract)

## Contract

- **Input:** `(event: dict, state: dict, node_id: str, diagnostics: list)`, matching
  [`_stream_jsonl`](stream-jsonl.md#contract)'s `on_event` calling convention exactly:
  - `event` — one parsed JSON object from a `codex exec --json` line.
  - `state` — the turn's accumulator, starting as `{"result_text": "", "session_id": None}`;
    mutated in place.
  - `node_id` — the workflow node id, used only for the live-echo log-line prefix.
  - `diagnostics` — the turn's diagnostics list; mutated in place (appended to, never read).
- **Output:** `None` — all effects are the in-place mutations to `state`/`diagnostics` below.
- **Raises:** nothing — a malformed `item`/`event` shape is read defensively (`.get(...)` with
  falsy defaults), never indexed directly.

## Algorithm

Dispatches on `event.get("type") or ""` (`etype`):

1. **`etype == "thread.started"`** → `state["session_id"] = event.get("thread_id") or
   state["session_id"]` — the thread id is codex's resumable session handle (used as `sid` in
   `codex exec resume ... <sid> -` on a later turn); falls back to the prior value so a
   missing/empty `thread_id` never clobbers one already captured.
2. **`etype == "item.completed"`** → inspect `item = event.get("item") or {}`:
   - `item.get("type") == "agent_message"` → if `item.get("text")` is non-empty, set
     `state["result_text"] = text` (last one wins — a turn with multiple `agent_message` items
     keeps only the final text) and echo `[{node_id}] {text.strip()[:500]}` to stdout (live
     progress, truncated to 500 chars).
   - else, `item.get("type") == "error"` or `item.get("error")` truthy → append
     `str(item)[:500]` to `diagnostics` (a structured error surfaced as a completed item rather
     than a distinct error-typed event).
3. **`"error" in etype or "fail" in etype`** (any other event type, e.g. `turn.failed`,
   `thread.error`) → append `json.dumps(event)[:500]` to `diagnostics` — the catch-all for
   codex's own error/failure event types that aren't `item.completed`.
4. Every other `etype` (e.g. `item.started`, `turn.completed`) is silently ignored — `_codex_on_event`
   only extracts the resume id, the final answer text, and error signals; it does not track turn
   progress beyond the live echo above.

Both `diagnostics` appends feed [`_stream_jsonl`](stream-jsonl.md#cap-abort-early-exit-on-a-spending-capusage-limit)'s
per-line cap-abort scan (run by its caller immediately after `on_event` returns) and, at the end of
the stream, [`_finalize_turn`](finalize-turn.md)'s classification — a codex cap or context-overflow
marker surfaces through whichever of these two branches captures the event carrying it, same as a
raw non-JSON diagnostic line.

## Related pieces

- [`_stream_jsonl`](stream-jsonl.md) — the generic event loop that calls this once per parsed JSON
  line and owns everything vocabulary-agnostic (spawn, timeout, cap-abort scan); `_codex_on_event`
  supplies only the codex-specific dispatch above.
- [`CodexBackend`](codex-backend.md) — the sole caller, passing `_codex_on_event` to
  `_stream_jsonl(cmd, node_id, timeout, prompt, _codex_on_event, cwd=cwd)` in `run_turn`.
- [`_finalize_turn`](finalize-turn.md) — reads `state["result_text"]`/`state["session_id"]` (as
  populated here) and the joined `diagnostics` to classify the turn once the stream ends.
- [`_copilot_on_event`](copilot-on-event.md) / [`_opencode_on_event`](opencode-on-event.md) — the
  analogous `on_event` adapters for the other two JSONL backends; each parses a different CLI's
  event shape into the same `state`/`diagnostics` contract.
