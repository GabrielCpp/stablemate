---
type: concept
slug: tool-summary
title: _tool_summary — one-line tool_use input summary
---
# _tool_summary — one-line tool_use input summary

Formats a Claude `tool_use` content block's `input` dict into a short, single-line
human-readable summary for the live-progress log line. Called once per `tool_use`
block by [`_emit_event`](emit-event.md#algorithm), which appends the result after the
tool name (`[{node_id}] ⚙ {name} {summary}`).

- code: `workhorse/workhorse/runner/agent.py::_tool_summary`

## Contract

- **Input:** `inp: dict` — a `tool_use` block's `input` field (the tool call's
  arguments), e.g. `{"file_path": "…"}` for a `Read`/`Edit` tool call or `{"command":
  "…"}` for a `Bash` call.
- **Output:** `str` — the first non-empty value found, whitespace-collapsed and
  truncated to 120 characters (with a trailing `…` if truncated); `""` if none of the
  known keys have a truthy value.
- **Raises:** nothing — every lookup is `dict.get`, defaulting to `None`/absent.

## Algorithm

1. **Scan a fixed key priority list**, in order: `file_path`, `path`, `command`,
   `pattern`, `url`, `query`, `description`. For each key, look up `inp.get(key)`.
2. **On the first truthy value found:**
   - Coerce to `str` and collapse all whitespace (`" ".join(str(value).split())`) —
     this flattens embedded newlines (e.g. a multi-line `Edit` `command`/`file_path`
     value) into one line so the log stays one line per tool call.
   - If the flattened string is longer than 120 characters, truncate to the first 120
     and append `…`; otherwise return it as-is.
3. **If no key in the priority list has a truthy value**, return `""` — the caller
   (`_emit_event`) then prints just `[{node_id}] ⚙ {name}` (right-stripped, no
   trailing space).

Only the *first* matching key is used — a block with both `file_path` and `command`
set (not expected from Claude's own tool schema, but not rejected either) reports
only the `file_path` summary.

## Related pieces

- [`_emit_event`](emit-event.md#algorithm) — the sole caller; invokes
  `_tool_summary(block.get("input", {}))` once per `tool_use` content block.
