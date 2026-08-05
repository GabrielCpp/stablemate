---
type: concept
slug: codex-on-event
title: codex _on_event — the Codex event-vocabulary adapter
---
# `_on_event` (codex) — the Codex event-vocabulary adapter

The `on_event` callback [`CodexBackend.run_turn`](codex-backend.md) hands to
[`stream_jsonl`](stream-jsonl.md): it knows `codex exec --json`'s own event vocabulary
(`thread.started`, `turn.completed`, `item.completed`, error/fail events) and is the only piece of
the shared JSONL loop that does — `stream_jsonl` itself is vocabulary-agnostic and just calls
`on_event(event, state, node_id)` once per parsed line. Its sibling adapters for the other JSONL
backends are [copilot's `_on_event`](copilot-on-event.md), [cline's `_on_event`](cline-on-event.md)
and [`_OpenCodeEvents.on_event`](opencode-on-event.md).

The name is unqualified: each adapter module owns exactly one `_on_event`, because module scope
already supplies the disambiguation a `_codex_`/`_copilot_` prefix used to. It is referred to here
by its module — `backends/codex.py` — not by a prefix in its own name.

- code: `workhorse/workhorse/runner/backends/codex.py::_on_event`
- extends: [stream_jsonl](stream-jsonl.md#contract)
- verify: `workhorse/tests/test_backends.py::test_codex_on_event_extracts_text_and_session`

## Contract

- **Input:** `(event: dict, state: TurnState, node_id: str)` — **three arguments**, matching
  [`stream_jsonl`](stream-jsonl.md#contract)'s calling convention exactly:
  - `event` — one parsed JSON object from a `codex exec --json` line.
  - `state` — the turn's [`TurnState`](finalize-turn.md#turnstate), mutated in place. Diagnostics
    go on `state.diagnostics`; there is no separate list argument.
  - `node_id` — the workflow node id, used only for the live-echo log-line prefix.
- **Output:** `None` — all effects are the in-place mutations to `state` below.
- **Raises:** nothing — a malformed `item`/`event` shape is read defensively (`.get(...)` with
  falsy defaults), never indexed directly.

## Algorithm

Dispatches on `event.get("type") or ""` (`etype`):

1. **`etype == "thread.started"`** → `state.session_id = event.get("thread_id") or
   state.session_id` — the thread id is codex's resumable session handle (used as `sid` in
   `codex exec resume ... <sid> -` on a later turn); falls back to the prior value so a
   missing/empty `thread_id` never clobbers one already captured.
2. **`etype == "turn.completed"`** → `state.usage = state.usage.merge(usage.normalize(event))`.
   Codex reports the turn's consumption here, and only tokens: under subscription auth it reports
   no cost at all, so these turns land with token counts and **no** `total_cost_usd` attribute
   rather than a fabricated `0.0` (absent ≠ zero, see
   [`TurnState.usage`](finalize-turn.md#turnstate)).
3. **`etype == "item.completed"`** → inspect `item = event.get("item") or {}`:
   - `item.get("type") == "agent_message"` → if `item.get("text")` is non-empty, set
     `state.result_text = text` (last one wins — a turn with multiple `agent_message` items keeps
     only the final text) and echo `[{node_id}] {text.strip()[:500]}` to stdout (live progress,
     truncated to 500 chars).
   - else, `item.get("type") == "error"` or `item.get("error")` truthy → append
     `str(item)[:500]` to `state.diagnostics` (a structured error surfaced as a completed item
     rather than a distinct error-typed event).
4. **`"error" in etype or "fail" in etype`** (any other event type, e.g. `turn.failed`,
   `thread.error`) → append `json.dumps(event)[:500]` to `state.diagnostics` — the catch-all for
   codex's own error/failure event types that aren't `item.completed`.
5. Every other `etype` (e.g. `item.started`) is silently ignored — this adapter extracts the resume
   id, the turn's usage, the final answer text, and error signals; it does not track turn progress
   beyond the live echo above.

Both `diagnostics` appends feed
[`stream_jsonl`](stream-jsonl.md#early-abort)'s per-line early-abort
scan (run by its caller immediately after `on_event` returns) and, at the end of the stream,
[`finalize_turn`](finalize-turn.md)'s classification — a codex cap or context-overflow marker
surfaces through whichever of these two branches captures the event carrying it, same as a raw
non-JSON diagnostic line.

## Related pieces

- [`stream_jsonl`](stream-jsonl.md) — the generic event loop that calls this once per parsed JSON
  line and owns everything vocabulary-agnostic (spawn, timeout, early-abort scan); this adapter
  supplies only the codex-specific dispatch above.
- [`CodexBackend`](codex-backend.md) — the sole caller, passing `_on_event` to
  `stream_jsonl(cmd, node_id, timeout, prompt, _on_event, resilience=resilience, cwd=cwd,
  env_extra=self.harness_env())` in `run_turn`.
- [`TurnState`](finalize-turn.md#turnstate) — the struct this mutates; the same one every backend
  fills, which is why one classifier can read all of them.
- [`finalize_turn`](finalize-turn.md) — reads the `result_text`/`session_id`/`usage` populated here
  and the joined diagnostics to classify the turn once the stream ends.
- [copilot's `_on_event`](copilot-on-event.md) / [cline's `_on_event`](cline-on-event.md) /
  [`_OpenCodeEvents.on_event`](opencode-on-event.md)
  — the analogous adapters for the other three JSONL backends; each parses a different CLI's event
  shape into the same `TurnState`.
