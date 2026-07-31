---
type: concept
slug: read-session-id
title: read_session_id — the persisted session-id reader
---
# read_session_id — the persisted session-id reader

The one-line lookup every JSONL backend's `run_turn` opens with: read the node's persisted
`.session_id` file, if any, and hand back the id to resume with. Shared by
[CodexBackend](codex-backend.md), [CopilotBackend](copilot-backend.md), and
[OpenCodeBackend](opencode-backend.md) — the three backends that resume a session by id (`codex exec
resume <sid>`, `copilot --session-id <sid>`, `opencode run --session <sid>`). `ClaudeBackend` and
[AiderBackend](aider-backend.md) don't call it: Claude reads the same file through its own inline
check in `runner/backends/claude.py` (it needs the id in two places, including the `/compact` turn),
and aider has no session-resume concept at all (single-message coder, ladder reframes on failure).

`session_id_path` itself is a per-node `Path` the caller ([`AgentRunner`](run-agent.md)) computes and
threads through every backend call; the file at that path is written by
[`classify_turn`](classify-turn.md) (via [`finalize_turn`](finalize-turn.md)) on a successful or
overflowing turn and by [`_compact_session`](compact-session.md), so `read_session_id` only ever
reads what a prior turn on the same node already persisted. It lives beside `finalize_turn` in
`runner/backends/turn.py` because they are the two ends of the same loop.

- code: `workhorse/workhorse/runner/backends/turn.py::read_session_id`

## Contract

- **Input:** `session_id_path: Path | None` — the node's `.session_id` file path, or `None` when the
  caller has no persisted-session concept for this call.
- **Output:** `str | None` — the persisted session id, or `None` when there is nothing to resume.
- **Raises:** nothing — a missing path, a missing file, and an empty/whitespace-only file all yield
  `None` rather than an error.

## Algorithm

1. If `session_id_path` is falsy (`None`) or the file it names doesn't exist, return `None`
   immediately.
2. Otherwise read the file's text and strip it.
3. Return the stripped text, or `None` if stripping left an empty string (an existing-but-blank
   `.session_id` file resumes nothing, same as a missing one).

## Related pieces

- [CodexBackend](codex-backend.md) / [CopilotBackend](copilot-backend.md) /
  [OpenCodeBackend](opencode-backend.md) — the three `run_turn` implementations that open with
  `sid = read_session_id(session_id_path)` and append their CLI's own resume flag
  (`exec resume <sid>` / `--session-id <sid>` / `--session <sid>`) only when `sid` is not `None`.
- [`finalize_turn`](finalize-turn.md) → [`classify_turn`](classify-turn.md) — writes the session id
  this function later reads, persisting `TurnState.session_id` to `session_id_path` on a successful
  or overflow turn, and recording the node→session mapping in
  [`sessions.jsonl`](classify-turn.md#record_session_map) alongside it.
- [`stream_jsonl`](stream-jsonl.md) — each backend calls `read_session_id` once, before building the
  argv that `stream_jsonl` then runs.
