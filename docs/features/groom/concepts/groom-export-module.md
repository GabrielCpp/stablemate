---
type: concept
slug: groom-export-module
title: Groom export module
---
# Groom export module

The export module materializes the [groom archive module](groom-archive-module.md)'s run-major archive into a by-node layout for analysis. The archive itself stores one run's entire transcript with its telemetry — the shape a debugger reads first. A dataset wants the transpose: all sessions that ever ran a given node, together, keyed by node name and source classifier so a prompt evaluation harness can compare competing models against identical tasks.

The export reads the store's turn index to classify sessions by their node, streams each session's transcript into one JSON file without holding anything larger than one line in memory, and writes an INDEX.json with one entry per session so a loader can list all runs and pick its filters without parsing every file. Nothing is kept in memory; a corpus that does not fit in memory therefore takes no time to materialize.

The output format is stable for interchange: every session is one JSON object in a side-by-side tree where a node's sessions are grouped by source classifier, and a downstream tool never needs to know about the run id, only about which node, which source, and which session — the coordinates written into each filename.

- code: groom/groom/export.py
- extends: [groom archive module](groom-archive-module.md)
- tests: groom/tests/test_export.py

## Methods

### export_by_node

- sig: `export_by_node(target_dir: Path, *, workflow: str = "", run: str = "", node: str = "", limit: int = 1_000_000) -> dict[str, Any]`
- abstract: false
- does: Materializes the archive under `target_dir` into the layout `<workflow>/<node>/<source>__<session_id>.json`, one JSON object per session with its streamed transcript
- does: Filters turns by workflow, run, node, and limits the total to `limit` rows from the store query, so a re-export of a subset is bounded
- does: Records sessions with no transcript as entries with an empty message list, rather than dropping them, so the export agrees with `transcript ls` about node run counts
- does: Creates `INDEX.json` at the root with one entry per written session, including metadata (task, source, session_id, run_id, workflow, generation, seq, time_created, n_messages, cwd, model, bytes, has_prompt) and the relative path to the session file
- raises: `OSError` if a session's transcript cannot be read, caught and logged before the next session
- verify: created(subject="session JSON files under target_dir")
- verify: created(subject="INDEX.json")
- returns: a dict with `sessions` (count of exported sessions) and `dir` (the target directory as a string)
- code: groom/groom/export.py::export_by_node

## Data format

### session-object

A JSON object written to `<workflow>/<node>/<source>__<session_id>.json`, streamed with these top-level keys:

- `task`: the node name from the turn record
- `source`: the source classifier, or `unknown` if absent
- `session_id`: the session's unique identifier
- `run_id`: the run this session belongs to
- `workflow`: the workflow name
- `generation`: the workflow generation
- `seq`: the sequence number within the generation
- `time_created`: ISO 8601 timestamp of session creation, or empty string on parse failure
- `head`: any head value from the turn record (arbitrary metadata)
- `messages`: an array of message objects, each with `role`, `content`, and optionally `model`
- `n_messages`: count of messages in the array
- `cwd`: the working directory if any message carries one, or empty string
- `model`: the model name if any message carries one, or empty string

Messages are extracted from transcripts in two formats:
- **JSONL format** (`transcript.jsonl`): each line is a record; a record with a `message` dict carrying `role` and `content` is kept; a record with top-level `role` and `content` is kept. Model is optional.
- **JSON format** (`transcript.json`): the payload is a dict with `messages` array; each item's `info` carries `modelID`, `providerID`, and `role`; each item's `parts` is the content array; model is reconstructed from provider/model if both are present.

Records without these shapes are dropped silently. Truncated lines (from byte-cap limits) are skipped.

### index-object

A JSON object written to `INDEX.json` with structure:
- `sessions`: count of session entries
- `records`: array of objects, one per session, each with the same fields as the session object plus `path` (the relative posix path to the JSON file)

## Helpers

### method-_safe

- sig: `_safe(value: str, fallback: str) -> str`
- abstract: false
- does: Sanitizes a string for use in a path component by replacing anything not alphanumeric, `.`, `_`, `-` with `_`, stripping leading/trailing unsafe chars, and falling back to `fallback` if the result is empty
- code: groom/groom/export.py::_safe
- verify: matches(subject="sanitized output", pattern="^[A-Za-z0-9._-]*$|^fallback$")

### method-_iso

- sig: `_iso(ts: Any) -> str`
- abstract: false
- does: Converts a Unix timestamp (float or string-float) to ISO 8601 format, returning an empty string on any parse or range error
- code: groom/groom/export.py::_iso

### method: _message_of

- sig: `_message_of(entry: dict[str, Any]) -> dict[str, Any] | None`
- abstract: false
- does: Extracts the message from a transcript entry, handling both nested and flat structures
- verify: json_path(path="$.role", matches=".+")
- does: Returns `None` if the entry has no role or content
- verify: absent(subject="message dict")
- does: Includes model in the result if present
- verify: json_path(path="$.model", matches=".+")
- code: groom/groom/export.py::_message_of

### method-_transcript_lines

- sig: `_transcript_lines(record: Path) -> Iterator[dict[str, Any]]`
- abstract: false
- does: Parses records from either `transcript.jsonl` (line-by-line) or `transcript.json` (array in payload)
- does: Skips empty lines and invalid JSON silently, recovering from truncated lines by continuing to the next record
- does: Handles both flat and nested message formats, extracting model and cwd when present
- code: groom/groom/export.py::_transcript_lines

### method: _write_session

- sig: `_write_session(row: dict[str, Any], target: Path) -> dict[str, Any]`
- abstract: false
- does: Writes one session as a JSON object to `target`, streaming messages to avoid holding the transcript in memory
- verify: created(subject="session JSON file at target")
- does: Writes to a `.part` suffix file first, then atomically renames so incomplete exports are not mistaken for complete ones
- verify: absent(subject=".json.part file after rename")
- does: Extracts `cwd` from the first message in the transcript that offers it, treating it as a session-level property
- does: Extracts `model` from the first message in the transcript that offers it, treating it as a session-level property
- does: Counts messages in the transcript and includes the count in the returned dict
- verify: json_path(path="$.n_messages", matches="[0-9]+")
- does: Creates parent directories if needed for the target file
- verify: created(subject="parent directory structure for target")
- returns: a dict with session metadata including task, source, session_id, run_id, workflow, generation, seq, time_created, head, n_messages, cwd, model, bytes, and has_prompt
- verify: json_path(path="$.session_id", matches=".*")
- raises: `OSError` if the file cannot be written
- verify: json_path(path="exception.type", equals="OSError")
- code: groom/groom/export.py::_write_session
- doc_status: |
  Extracted three normative bullets that form one claim ("Extracts cwd and model from messages") — `cwd` and `model` are optional fields that either come from messages or default to empty string. A QA scenario must provide specific message inputs to discriminate extraction from default values. The extracts are observable only with knowledge of the input transcript; two separate test scenarios (one with cwd in messages, one without) would verify the behavior, but a single observation cannot cover both. These bullets remain unbound pending QA scenarios that provide concrete test inputs.
  
  The `session_id` check uses a generic `matches` rather than a specific value because the session_id comes from the input row and depends on the QA scenario's setup. A scenario providing `session_id="test-123"` would verify `equals="test-123"` in practice.

