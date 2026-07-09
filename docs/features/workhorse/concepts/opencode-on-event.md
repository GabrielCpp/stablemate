---
type: concept
slug: opencode-on-event
title: _opencode_on_event — the OpenCode event-vocabulary adapter
---
# _opencode_on_event — the OpenCode event-vocabulary adapter

The `on_event` callback [`OpenCodeBackend.run_turn`](#related-pieces) hands to
[`_stream_jsonl`](stream-jsonl.md): it knows `opencode run --format json`'s own event vocabulary
(`text`, `error`, and other NDJSON event types keyed by `sessionID`) and is the only piece of the
shared JSONL loop that does — `_stream_jsonl` itself is vocabulary-agnostic and just calls
`on_event(event, state, node_id, diagnostics)` once per parsed line. Its sibling adapters for the
other JSONL backends are [`_codex_on_event`](codex-on-event.md) and
[`_copilot_on_event`](copilot-on-event.md).

- code: `workhorse/workhorse/runner/backends.py::_opencode_on_event`
- extends: [_stream_jsonl](stream-jsonl.md#contract)
- verify: `workhorse/tests/test_backends.py::test_opencode_on_event_text_session_and_error`

## Contract

- **Input:** `(event: dict, state: dict, node_id: str, diagnostics: list)`, matching
  [`_stream_jsonl`](stream-jsonl.md#contract)'s `on_event` calling convention exactly:
  - `event` — one parsed JSON object from an `opencode run --format json` line.
  - `state` — the turn's accumulator, starting as `{"result_text": "", "session_id": None}`;
    mutated in place. `_opencode_on_event` also lazily adds a private `_text_parts` key (see
    below) — not part of `_stream_jsonl`'s own contract, internal to this adapter only.
  - `node_id` — the workflow node id, used only for the live-echo log-line prefix.
  - `diagnostics` — the turn's diagnostics list; mutated in place (appended to, never read).
- **Output:** `None` — all effects are the in-place mutations to `state`/`diagnostics` below.
- **Raises:** nothing — a malformed `event`/`part`/`error` shape is read defensively (`.get(...)`
  with falsy defaults), never indexed directly.

## Algorithm

1. **Session id — checked on every event, independent of `type`.** `sid = event.get("sessionID")`;
   if truthy, `state["session_id"] = sid`. Unlike codex (`thread.started`-only) and copilot
   (`result`-only), opencode stamps `sessionID` on every NDJSON line, so the adapter captures it
   unconditionally rather than gating on a specific event type; a missing/empty `sessionID` on any
   one line leaves the prior captured value untouched (no unconditional overwrite with a falsy
   value). This is the resume handle used as `sid` in a later turn's `opencode run --session <sid>`
   (see [`OpenCodeBackend.run_turn`](#related-pieces)).
2. Dispatch on `etype = event.get("type") or ""`:
   - **`etype == "text"`** → accumulate a streamed answer chunk:
     1. `part = event.get("part") or {}`; `text = part.get("text") or ""`.
     2. If `text` is empty, do nothing further (no diagnostic, no echo).
     3. Otherwise: `parts = state.setdefault("_text_parts", {})` — a dict keyed by part id, created
        on first use and persisted across calls on the same `state`.
     4. `parts[part.get("id") or len(parts)] = text` — key by `part["id"]` when opencode supplies
        one; fall back to the current part count as a positional key when it doesn't, so an
        unkeyed part still gets its own slot rather than colliding with `""`.
     5. `state["result_text"] = "\n".join(parts.values())` — every distinct part id accumulates
        (unlike codex/copilot's "last message wins"), newline-joined in **insertion order** (Python
        dict order), so multiple `text` parts in one turn are all preserved and concatenated rather
        than only the final one kept. A **repeated** part id instead overwrites that slot in place
        (streamed-token growth of the same part), so `result_text` reflects the latest content for
        that id without duplicating it.
     6. Echo `[{node_id}] {text.strip()[:500]}` to stdout (live progress, truncated to 500 chars) —
        one echo per `text` event, i.e. per streamed chunk, not per accumulated total.
   - **`etype == "error"`** → append a diagnostic:
     1. `err = event.get("error") or {}`; `data = err.get("data") or {}`.
     2. `msg = data.get("message") or err.get("name") or json.dumps(event)[:300]` — prefer the
        structured message, fall back to the error's `name`, fall back to the whole event
        JSON-dumped and truncated to 300 chars if neither is present.
     3. Append `str(msg)[:500]` to `diagnostics`.
   - Every other `etype` (e.g. `step_start`, `step_finish`, tool-call/progress events opencode may
     emit) is silently ignored beyond the unconditional session-id capture in step 1 —
     `_opencode_on_event` only extracts the resume id, the accumulated answer text, and error
     signals; it does not track turn progress beyond the live echo above.

The `diagnostics` append feeds [`_stream_jsonl`](stream-jsonl.md#cap-abort-early-exit-on-a-spending-capurl-limit)'s
per-line cap-abort scan (run by its caller immediately after `on_event` returns) and, at the end of
the stream, [`_finalize_turn`](finalize-turn.md)'s classification — an opencode structured error
event surfaces through this branch the same way a raw non-JSON `--print-logs` diagnostic line does
(opencode's own quota/limit errors more often arrive as *unparsed* log lines caught by
`_stream_jsonl`'s JSON-decode-fails branch instead, per `test_opencode_cap_log_line_aborts_stream_early`;
this `error`-event branch is the structured-event counterpart, per
`test_opencode_cap_structured_error_event_aborts_stream_early`).

## Related pieces

- [`_stream_jsonl`](stream-jsonl.md) — the generic event loop that calls this once per parsed JSON
  line and owns everything vocabulary-agnostic (spawn, timeout, cap-abort scan);
  `_opencode_on_event` supplies only the opencode-specific dispatch above.
- `OpenCodeBackend.run_turn` (`workhorse/workhorse/runner/backends.py::OpenCodeBackend`) — the sole
  caller, passing `_opencode_on_event` to `_stream_jsonl(cmd, node_id, timeout, None,
  _opencode_on_event, cwd=cwd)` in `run_turn` (`None` stdin, since opencode takes its prompt as a
  positional argv message rather than on stdin). Not yet modeled as its own concept node.
- [`_finalize_turn`](finalize-turn.md) — reads `state["result_text"]`/`state["session_id"]` (as
  populated here) and the joined `diagnostics` to classify the turn once the stream ends.
- [`_codex_on_event`](codex-on-event.md) / [`_copilot_on_event`](copilot-on-event.md) — the
  analogous `on_event` adapters for the other two JSONL backends; each parses a different CLI's
  event shape into the same `state`/`diagnostics` contract. Both codex and copilot keep only the
  **last** message text on repeat events; `_opencode_on_event` is the odd one out, **accumulating**
  every distinct `text` part.
