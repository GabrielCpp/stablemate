---
type: concept
slug: read-session-id
title: _read_session_id — the persisted session-id reader
---
# _read_session_id — the persisted session-id reader

The one-line lookup every JSONL backend's `run_turn` opens with: read the node's persisted
`.session_id` file, if any, and hand back the id to resume with. Shared by
[CodexBackend](codex-backend.md), [CopilotBackend](copilot-backend.md), and
[OpenCodeBackend](opencode-backend.md) — the three backends that resume a session by id (`codex exec
resume <sid>`, `copilot --session-id <sid>`, `opencode run --session <sid>`). `ClaudeBackend` and
[AiderBackend](aider-backend.md) don't call it: Claude resumes through its own inline check in
`agent.py` (`_run_claude_cli`), and Aider has no session-resume concept at all (single-message coder,
ladder reframes on failure).

`session_id_path` itself is a per-node `Path` the caller (`runner/agent.py::run_agent`) computes and
threads through every backend call; the file at that path is written by
[`classify_turn`](classify-turn.md) (via [`_finalize_turn`](finalize-turn.md)) on a successful turn
and by `_compact_session`, so `_read_session_id` only ever reads what a prior turn on the same node
already persisted.

- code: `workhorse/workhorse/runner/backends.py::_read_session_id`

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
  `sid = _read_session_id(session_id_path)` and append their CLI's own resume flag
  (`exec resume <sid>` / `--session-id <sid>` / `--session <sid>`) only when `sid` is not `None`.
- [`_finalize_turn`](finalize-turn.md) → [`classify_turn`](classify-turn.md) — writes the session id
  this function later reads, persisting `state["session_id"]` to `session_id_path` on a successful or
  overflow turn.
- [`_stream_jsonl`](stream-jsonl.md) — each backend calls `_read_session_id` once, before building the
  argv that `_stream_jsonl` then runs.

