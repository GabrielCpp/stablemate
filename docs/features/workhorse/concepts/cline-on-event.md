---
type: concept
slug: cline-on-event
title: _on_event — the cline event-vocabulary adapter
---
# `_on_event` — the cline event-vocabulary adapter

The `on_event` callback [`ClineBackend.run_turn`](cline-backend.md#contract) hands to
[`stream_jsonl`](stream-jsonl.md): it knows `cline --json`'s own event vocabulary (`run_result`,
`hook_event`, `agent_event`) and is the only piece of the shared JSONL loop that does —
`stream_jsonl` itself is vocabulary-agnostic and just calls `on_event(event, state, node_id)` once
per parsed line. Its sibling adapters for the other JSONL backends are
[codex's `_on_event`](codex-on-event.md), [copilot's `_on_event`](copilot-on-event.md) and
[`_OpenCodeEvents.on_event`](opencode-on-event.md).

Like codex's and copilot's it is a **module-level function**, not a per-turn object: cline already
assembles the answer and repeats it whole on the terminal event, so nothing has to be accumulated
across calls (contrast [opencode](opencode-on-event.md), whose text parts are the reason that one
adapter needed state).

Every event shape below was captured from a live turn (CLI 3.0.50, 2026-08-05), not inferred from
documentation.

- code: `workhorse/workhorse/runner/backends/cline.py::_on_event`
- extends: [stream_jsonl](stream-jsonl.md#contract)
- verify: `workhorse/tests/test_backends.py::test_cline_on_event_reads_the_terminal_result`,
  `workhorse/tests/test_backends.py::test_cline_reports_an_unclean_finish_reason_as_a_diagnostic`,
  `workhorse/tests/test_backends.py::test_cline_per_iteration_usage_is_not_double_counted`,
  `workhorse/tests/test_usage.py::test_cline_reports_tokens_cost_and_duration`

## Contract

- **Input:** `(event: dict, state: TurnState, node_id: str)` — three arguments, matching
  [`stream_jsonl`](stream-jsonl.md#contract)'s calling convention exactly:
  - `event` — one parsed JSON object from a `cline --json` line.
  - `state` — the turn's [`TurnState`](finalize-turn.md#turnstate), mutated in place. Diagnostics go
    on `state.diagnostics`; there is no separate list argument.
  - `node_id` — the workflow node id, used only for the live-echo log-line prefix.
- **Output:** `None` — all effects are the in-place mutations to `state` below.
- **Raises:** nothing — every nested shape is read defensively (`.get(...)` with falsy defaults),
  never indexed directly.

## Algorithm

Dispatch on `etype = event.get("type") or ""`:

- **`"hook_event"`** → the resume handle. If `event["taskId"]` is truthy,
  `state.session_id = event["taskId"]`. It arrives here rather than on the terminal event, so it is
  captured whenever it shows up; this is the id a later turn passes as `cline --id <sid>` (see
  [`ClineBackend.run_turn`](cline-backend.md#contract)).
- **`"run_result"`** → the terminal event, and the one that matters:
  1. `state.result_text = (event.get("text") or "").strip()` — the answer is **taken** from the
     terminal event rather than re-derived from the streamed content parts. Cline already assembled
     it, and accumulating a second copy here would be a second implementation of the same thing
     that could disagree with the first.
  2. `state.usage = state.usage.merge(usage.normalize(event))` — `run_result.usage` carries
     `inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens` and `totalCost`, and the
     event itself carries `durationMs`. That is tokens, the cache split, real money **and**
     duration from one event — the fullest report of any backend.
  3. `reason = event.get("finishReason") or ""`; anything truthy that isn't `"completed"` appends
     `f"cline finishReason={reason}"` to `state.diagnostics`. The adapter states cline's own verdict
     and stops there — whether that verdict is transient, an overflow or fatal is
     [`classify_turn`](classify-turn.md#ladder-first-match-wins)'s call, not this module's. A clean
     completion says nothing.
- **`"agent_event"`** → the live echo only. On an inner `{"type": "content_end", "contentType":
  "text"}` with non-empty text, print `[{node_id}] {text[:500]}`; nothing is stored.
  The inner `{"type": "usage", ...}` event is **deliberately ignored**: cline emits it per
  *iteration* while `run_result.usage` is already the turn's total, so folding both would bill every
  turn twice. (Opencode is the opposite case — there the per-step events are the only report, so
  [they must be summed](opencode-on-event.md).)
- **Any `etype` containing `"error"`** → append `json.dumps(event)[:500]` to `state.diagnostics`,
  which feeds [`stream_jsonl`](stream-jsonl.md#early-abort)'s per-line early-abort scan and, at the
  end of the stream, [`finalize_turn`](finalize-turn.md)'s classification.

## Related pieces

- [`stream_jsonl`](stream-jsonl.md) — the generic event loop that calls this once per parsed JSON
  line and owns everything vocabulary-agnostic (spawn, timeout, early-abort scan).
- [`ClineBackend`](cline-backend.md) — the sole caller, passing this function to
  `stream_jsonl(cmd, node_id, timeout, None, _on_event, ...)` in `run_turn`.
- [`TurnState`](finalize-turn.md#turnstate) — the struct this mutates; the same one every backend
  fills, which is why one classifier can read all of them.
- [`finalize_turn`](finalize-turn.md) — reads the `result_text`/`session_id`/`usage` populated here
  and the joined diagnostics to classify the turn once the stream ends.
- [codex's `_on_event`](codex-on-event.md) / [copilot's `_on_event`](copilot-on-event.md) /
  [`_OpenCodeEvents.on_event`](opencode-on-event.md) — the analogous adapters for the other three
  JSONL backends; each parses a different CLI's event shape into the same `TurnState`.
