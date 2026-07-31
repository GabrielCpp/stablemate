---
type: concept
slug: opencode-on-event
title: _OpenCodeEvents.on_event — the OpenCode event-vocabulary adapter
---
# `_OpenCodeEvents.on_event` — the OpenCode event-vocabulary adapter

The `on_event` callback [`OpenCodeBackend.run_turn`](opencode-backend.md#contract) hands to
[`stream_jsonl`](stream-jsonl.md): it knows `opencode run --format json`'s own event vocabulary
(`text`, `step_finish`, `error`, and other NDJSON event types keyed by `sessionID`) and is the only
piece of the shared JSONL loop that does — `stream_jsonl` itself is vocabulary-agnostic and just
calls `on_event(event, state, node_id)` once per parsed line. Its sibling adapters for the other
JSONL backends are [codex's `_on_event`](codex-on-event.md) and
[copilot's `_on_event`](copilot-on-event.md).

Alone among the three it is **not** a module-level function but a **bound method on a per-turn
object**. OpenCode streams one answer as several `text` parts that have to be reassembled in
arrival order, so this adapter — and only this adapter — carries state across the calls of a single
turn. That state lives on `_OpenCodeEvents`, a `@dataclass(slots=True)` instantiated fresh inside
each `run_turn`, rather than on the [`TurnState`](finalize-turn.md#turnstate) every backend shares:
a struct shared by N implementations holding one implementation's private key is exactly the shape
the shared module must not have. A fresh instance per turn is also what makes leakage between turns
structurally impossible rather than a discipline
(`test_opencode_text_parts_do_not_leak_between_turns`).

- code: `workhorse/workhorse/runner/backends/opencode.py::_OpenCodeEvents.on_event`
- extends: [stream_jsonl](stream-jsonl.md#contract)
- verify: `workhorse/tests/test_backends.py::test_opencode_on_event_text_session_and_error`,
  `workhorse/tests/test_backends.py::test_opencode_text_parts_do_not_leak_between_turns`,
  `workhorse/tests/test_backends.py::test_opencode_cap_structured_error_event_aborts_stream_early`

## The `_OpenCodeEvents` instance

- code: `workhorse/workhorse/runner/backends/opencode.py::_OpenCodeEvents`

A `@dataclass(slots=True)` with a single field:

- `parts: dict[str | int, str]` — the turn's accumulated answer chunks, keyed by opencode's own
  part id (or by positional index when a part carries none). Defaults to an empty dict per
  instance, so nothing survives the turn that created it.

`run_turn` constructs one and hands `stream_jsonl` the **bound** `_OpenCodeEvents().on_event`; the
loop never sees the instance and needs no notion that this backend keeps state at all.

## Contract

- **Input:** `(event: dict, state: TurnState, node_id: str)` — **three arguments**, matching
  [`stream_jsonl`](stream-jsonl.md#contract)'s calling convention exactly (`self` is already bound):
  - `event` — one parsed JSON object from an `opencode run --format json` line.
  - `state` — the turn's [`TurnState`](finalize-turn.md#turnstate), mutated in place. Diagnostics go
    on `state.diagnostics`; there is no separate list argument, and no adapter-private key is added
    to it — the text parts live on `self.parts` instead.
  - `node_id` — the workflow node id, used only for the live-echo log-line prefix.
- **Output:** `None` — all effects are the in-place mutations to `state` and `self.parts` below.
- **Raises:** nothing — a malformed `event`/`part`/`error` shape is read defensively (`.get(...)`
  with falsy defaults), never indexed directly.

## Algorithm

1. **Session id — checked on every event, independent of `type`.** `sid = event.get("sessionID")`;
   if truthy, `state.session_id = sid`. Unlike codex (`thread.started`-only) and copilot
   (`result`-only), opencode stamps `sessionID` on every NDJSON line, so the adapter captures it
   unconditionally rather than gating on a specific event type; a missing/empty `sessionID` on any
   one line leaves the prior captured value untouched (no unconditional overwrite with a falsy
   value). This is the resume handle used as `sid` in a later turn's `opencode run --session <sid>`
   (see [`OpenCodeBackend.run_turn`](opencode-backend.md#contract)).
2. Dispatch on `etype = event.get("type") or ""`:
   - **`etype == "step_finish"`** → `state.usage = state.usage.merge(usage.normalize(event))`.
     OpenCode reports consumption per completed step, and a turn can have several, so this is a
     **merge** rather than an assignment — the counts add up across steps instead of the last step
     replacing the total. Fields opencode omits stay absent rather than becoming `0.0`
     (absent ≠ zero, see [`TurnState.usage`](finalize-turn.md#turnstate)).
   - **`etype == "text"`** → accumulate a streamed answer chunk:
     1. `part = event.get("part") or {}`; `text = part.get("text") or ""`.
     2. If `text` is empty, do nothing further (no diagnostic, no echo).
     3. `self.parts[part.get("id") or len(self.parts)] = text` — key by `part["id"]` when opencode
        supplies one; fall back to the current part count as a positional key when it doesn't, so an
        unkeyed part still gets its own slot rather than colliding with `""`.
     4. `state.result_text = "\n".join(self.parts.values())` — every distinct part id accumulates
        (unlike codex/copilot's "last message wins"), newline-joined in **insertion order** (Python
        dict order), so multiple `text` parts in one turn are all preserved and concatenated rather
        than only the final one kept. A **repeated** part id instead overwrites that slot in place
        (streamed-token growth of the same part), so `result_text` reflects the latest content for
        that id without duplicating it.
     5. Echo `[{node_id}] {text.strip()[:500]}` to stdout (live progress, truncated to 500 chars) —
        one echo per `text` event, i.e. per streamed chunk, not per accumulated total.
   - **`etype == "error"`** → append a diagnostic:
     1. `err = event.get("error") or {}`; `data = err.get("data") or {}`.
     2. `msg = data.get("message") or err.get("name") or json.dumps(event)[:300]` — prefer the
        structured message, fall back to the error's `name`, fall back to the whole event
        JSON-dumped and truncated to 300 chars if neither is present.
     3. Append `str(msg)[:500]` to `state.diagnostics`.
   - Every other `etype` (e.g. `step_start`, tool-call/progress events opencode may emit) is
     silently ignored beyond the unconditional session-id capture in step 1 — this adapter extracts
     the resume id, the accumulated answer text, the usage, and error signals; it does not track
     turn progress beyond the live echo above.

The `state.diagnostics` append feeds
[`stream_jsonl`](stream-jsonl.md#early-abort)'s per-line early-abort
scan (run by its caller immediately after `on_event` returns) and, at the end of the stream,
[`finalize_turn`](finalize-turn.md)'s classification — an opencode structured error event surfaces
through this branch the same way a raw non-JSON `--print-logs` diagnostic line does (opencode's own
quota/limit errors more often arrive as *unparsed* log lines caught by `stream_jsonl`'s
JSON-decode-fails branch instead, per `test_opencode_cap_log_line_aborts_stream_early`; this
`error`-event branch is the structured-event counterpart, per
`test_opencode_cap_structured_error_event_aborts_stream_early`).

## Related pieces

- [`stream_jsonl`](stream-jsonl.md) — the generic event loop that calls this once per parsed JSON
  line and owns everything vocabulary-agnostic (spawn, timeout, early-abort scan); this adapter
  supplies only the opencode-specific dispatch above.
- [`OpenCodeBackend`](opencode-backend.md) — the sole caller, passing a freshly constructed
  `_OpenCodeEvents().on_event` to `stream_jsonl(cmd, node_id, timeout, None,
  _OpenCodeEvents().on_event, resilience=resilience, cwd=cwd, env_extra=self.harness_env())` in
  `run_turn` (`None` stdin, since opencode takes its prompt as a positional argv message rather
  than on stdin).
- [`TurnState`](finalize-turn.md#turnstate) — the struct this mutates; the same one every backend
  fills, which is why one classifier can read all of them — and, deliberately, *not* where this
  adapter's `parts` live.
- [`finalize_turn`](finalize-turn.md) — reads the `result_text`/`session_id`/`usage` populated here
  and the joined diagnostics to classify the turn once the stream ends.
- [codex's `_on_event`](codex-on-event.md) / [copilot's `_on_event`](copilot-on-event.md) — the
  analogous adapters for the other two JSONL backends; each parses a different CLI's event shape
  into the same `TurnState`. Both keep only the **last** message text on repeat events; this one is
  the odd one out, **accumulating** every distinct `text` part — which is exactly why it is the
  only adapter that needed an object.
