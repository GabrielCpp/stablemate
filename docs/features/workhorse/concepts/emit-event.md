---
type: concept
slug: emit-event
title: _emit_event — live-echo printer for stream-json events
---
# _emit_event — live-echo printer for stream-json events

Prints a concise, human-readable line to stdout for a successfully-parsed Claude
`stream-json` event, so an unattended run's log shows live progress. Called once per
event, unconditionally, by [`_stream_events`](stream-events.md#algorithm)'s `on_line`
callback — independent of that function's own `result_text`/`session_id`/`rate_limited`
state accumulation; `_emit_event` never mutates turn state and its return value is
always discarded.

- code: `workhorse/workhorse/runner/agent.py::_emit_event`

## Contract

- **Input:**
  - `node_id: str` — the workflow node id, printed as the `[{node_id}]` line prefix.
  - `event: dict` — one parsed JSON object from a `claude --output-format stream-json` line.
- **Output:** `None` — the sole effect is stdout writes (`print(..., flush=True)`); a
  line is flushed immediately so live tailing (e.g. `docker compose logs -f`) sees it
  without buffering delay.
- **Raises:** nothing — reads `event` defensively (`.get(...)` with falsy defaults,
  `or []` on the content list), never indexes it directly.

## Algorithm

Dispatches on `event.get("type")` (`etype`); any other `etype` is silently ignored (no
line printed):

1. **`etype == "assistant"`** — iterate `event.get("message", {}).get("content", []) or
   []`; for each content block, dispatch on `block.get("type")` (`btype`):
   - **`btype == "text"`** — strip `block.get("text", "")`; if non-empty, print
     `[{node_id}] {text}`. An empty/whitespace-only text block prints nothing.
   - **`btype == "tool_use"`** — print `[{node_id}] ⚙ {name} {summary}`, right-stripped
     (so a blank `summary` leaves no trailing space), where `name = block.get("name",
     "?")` and `summary = `[`_tool_summary`](tool-summary.md#algorithm)`(block.get(
     "input", {}))`.
   - any other `btype` — ignored.
2. **`etype == "result"`** — print `[{node_id}] ✓ result received`, appending
   ` ({dur} ms)` when `event.get("duration_ms")` is truthy (`dur`); omitted entirely
   when absent/falsy.

## Related pieces

- [`_stream_events`](stream-events.md#algorithm) — the sole caller; invokes
  `_emit_event(node_id, event)` once per successfully-parsed line, for every event
  type, regardless of whether that event also updates `_stream_events`'s own
  `result_text`/`session_id`/`rate_limited` accumulator.
- [`_tool_summary`](tool-summary.md) — formats a `tool_use` block's `input` dict into
  the short one-line summary appended after the tool name.
