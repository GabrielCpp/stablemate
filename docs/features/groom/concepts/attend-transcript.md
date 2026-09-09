---
type: concept
slug: attend-transcript
title: Attendant session transcript
---
# Attendant session transcript

Persistent storage and rendering of attendant session transcripts. The CLI stores session transcripts in `~/.claude/projects/`, which it may prune at any time; this module copies them into groom's own transcript tree (`transcripts/attend/`) so they survive as a durable audit trail of what attendants did across multiple runs and seasons. Transcripts are rendered as readable prose for display in the groom dashboard pane.

- code: `groom/groom/attend_transcript.py`
- tests: `groom/tests/test_attend.py`

## Storage and copying

Session transcripts live at `<groom data dir>/transcripts/attend/<session_id>/`, a flat structure outside the run-major archive tree so they are never swept away when a run is frozen. Each session's directory contains:

- `<session_id>.jsonl` — the main transcript, one JSON record per message
- `<session_id>/` — a subdirectory of subagent sidechains, one `.jsonl` file per spawned subagent

The copy is **complete** or **absent**: a session partially copied is treated as missing, and the copy is retried on the next read.

### method: copy_session
- sig: `(session_id: str) -> int`
- does: if `session_id` is empty, return 0 without resolving a store
- verify: json_path(path="result", equals=0)
- does: resolve the CLI's store location for this session via `workhorse.runner.transcript._claude_store()`
- verify: persists(subject="transcript files in groom's attend directory")
- does: if that lookup raises, log at debug level and return 0
- verify: json_path(path="result", equals=0)
- does: if the lookup returns no sources, return 0
- verify: json_path(path="result", equals=0)
- does: create the target session directory, then copy all files and directories from the resolved store into it
- verify: created(subject="session directory under attend_root()")
- does: sum the byte size of all copied files
- verify: json_path(path="result", matches="^[1-9][0-9]*$")
- returns: the bytes written to disk, when the copy succeeds
- verify: json_path(path="result", matches="^[1-9][0-9]*$")
- returns: 0 if the session was not found or could not be copied
- verify: json_path(path="result", equals=0)
- raises: `OSError` during copy is caught rather than propagated, and logged at warning level
- verify: json_path(path="exception.type", absent=true)
- returns: the partial byte count copied so far, when the copy raised `OSError` partway through
- verify: json_path(path="result", matches="^[1-9][0-9]*$")
- code: `groom/groom/attend_transcript.py::copy_session`

This is the main public API. It is called at attendant exit time (`spawn_headless` spawns a daemon thread that calls it) and on first read (`ensure_body` retries if `has_body` returned false). Copy failure is a poorer audit trail but not a failed attendance, so errors are logged but not propagated.

### method: has_body
- sig: `(session_id: str) -> bool`
- does: return `True` if the session directory exists and contains at least one `.jsonl` file anywhere under it (including in the sidechains subdirectory)
- verify: json_path(path="result", equals=true)
- does: return `False` if the session directory does not exist, or exists but contains no `.jsonl` file
- verify: json_path(path="result", equals=false)
- code: `groom/groom/attend_transcript.py::has_body`

### method: ensure_body
- sig: `(session_id: str) -> bool`
- does: if `has_body()` returns `True`, return `True` immediately without copying
- verify: json_path(path="result", equals=true)
- does: otherwise, call `copy_session()` to copy the transcript from the CLI store, then call `has_body()` again and return its result
- verify: json_path(path="result", equals=true)
- returns: `True` if the transcript is present after copying, `False` if the copy did not produce any transcript data
- verify: json_path(path="result", equals=true)
- code: `groom/groom/attend_transcript.py::ensure_body`

Called by the attendant pane API before rendering; retries the copy exactly once if it did not happen at exit time.

### attend_root
- sig: `() -> Path`
- persistence: attend-root — `<groom data dir>/transcripts/attend`, the sibling of the run-major archive tree described above
- verify: json_path(path="result", matches=".*/transcripts/attend$")
- code: `groom/groom/attend_transcript.py::attend_root`

### session_dir
- sig: `(session_id: str) -> Path`
- consistency: session-dir — the session directory is `<attend_root()>/<session_id>`, so a session's directory is always addressable from its id alone
- verify: json_path(path="result", matches=".*/transcripts/attend/.+$")
- code: `groom/groom/attend_transcript.py::session_dir`

## Rendering

Transcripts are rendered as readable prose for display in the dashboard. Tool calls are collapsed to one line (their subject), full JSON is converted to prose, and thinking tokens are dropped.

### method: render_session
- sig: `(session_id: str) -> dict[str, Any]`
- does: read the main transcript file via `_entries()` if it exists
- verify: json_path(path="result.entries", matches=".+")
- does: read sidechain transcript files via `_entries()` if they exist, adding a divider before each sidechain's entries
- verify: created(subject="divider entries before sidechain content")
- returns: a dict with `session_id` (string), `present` (true if any entries), `path` (session directory), and `entries` (list of rendered entries)
- verify: json_path(path="result.present", matches="true|false")
- code: `groom/groom/attend_transcript.py::render_session`

### Parsed entries

Entries are one of four kinds:

- `message` — a text message from assistant or user. Fields: `kind`, `role`, `text`, `sidechain`
- `tool` — a tool call or its result. Fields: `kind`, `name` (tool name), `summary` (one-line identifying the call subject), `detail` (the arguments as prose), `result` (tool result, truncated), `failed` (whether the result was marked an error), `sidechain`
- `divider` — a separator between sidechains. Fields: `kind`, `label`

Tool calls are rendered collapsed, and tool results are paired back to their calls by `tool_use_id`. Orphaned results (a result without a matching call) appear as standalone `tool` entries. Text is extracted from message content blocks and joined; all other content types (images, code blocks, etc.) are dropped from the prose view.

### method: _entries
- sig: `(path: Path, sidechain: bool = False) -> list[dict[str, Any]]`
- does: read the JSONL file, parsing each line as a message record
- verify: json_path(path="result[0]", matches="kind")
- does: extract the message body and role from each record
- verify: json_path(path="result", matches="role")
- does: extract tool calls and tool results from each record
- verify: json_path(path="result", matches="tool_use_id")
- does: pair each tool result back to its call by `tool_use_id`
- verify: json_path(path="result[*]", matches="tool_use_id")
- does: render tool calls with `_tool_summary()` and `_detail_of()`, tool results truncated to `MAX_DETAIL_CHARS` (4000)
- verify: json_path(path="result", matches="summary")
- does: return an ordered list of rendered entries
- verify: json_path(path="result", matches=".*")
- does: skip a malformed JSON line silently rather than raising
- verify: json_path(path="result", matches=".*")
- does: on a file read failure, return an empty list rather than raising
- verify: count(subject="result", equals=0)
- returns: list of entry dicts with `kind`, role/name/summary/detail/result fields as above
- verify: json_path(path="result[*]", matches="kind")
- code: `groom/groom/attend_transcript.py::_entries`

### method: _tool_summary
- sig: `(name: str, args: Any) -> str`
- does: check `file_path`, `path`, `command`, `pattern`, `query`, `url`, `prompt` in that order and, for the first one holding a non-empty string, return `name: <first line of that value, truncated to 160 chars>`
- verify: json_path(path="result", equals="Read: /tmp/x")
- does: if none of those keys hold a non-empty string, return the tool name alone
- verify: json_path(path="result", equals="Read")
- code: `groom/groom/attend_transcript.py::_tool_summary`

### method: _detail_of
- sig: `(args: Any) -> str`
- does: if `args` is a dict, render one line per item as `key: value`, JSON-encoding the value when it is not already a string, joined with `\n`
- verify: json_path(path="result", equals="path: /tmp/x\ncommand: 3")
- does: if `args` is a plain string, return it unchanged
- verify: json_path(path="result", equals="hello world")
- does: if `args` is neither a dict nor a string, return an empty string
- verify: json_path(path="result", equals="")
- does: truncate the result to `MAX_DETAIL_CHARS` (4000) characters
- verify: json_path(path="result", matches="^.{4000}$")
- code: `groom/groom/attend_transcript.py::_detail_of`

### _result_text
- sig: `(content: Any) -> str`
- does: extract text from a tool result, handling both plain strings and lists of content blocks (extracting only text-type blocks); truncate to `MAX_DETAIL_CHARS`
- code: `groom/groom/attend_transcript.py::_result_text`

### method: _text_of
- sig: `(content: Any) -> str`
- does: when content is a string, return it with leading and trailing whitespace removed
- verify: json_path(path="result", equals="hello world")
- does: when content is neither a string nor a list, return an empty string
- verify: json_path(path="result", equals="")
- does: when content is a list, extract all text blocks from the message body (where each block is a dict with `type == "text"`), join them with blank lines, and drop non-text blocks (thinking, images, etc.)
- verify: json_path(path="result", equals="hello\n\nworld")
- code: `groom/groom/attend_transcript.py::_text_of`

## Configuration

Two module-level constants control rendering:

- `MAX_SESSION_BYTES` — ceiling on one copied session (default: `turns.MAX_RECORD_BYTES`). An attendant that read a very large tree is still a record worth having; it is not worth an unbounded copy.
- `MAX_DETAIL_CHARS` — how much of one tool result or arguments dict the pane displays (default: 4000). A 2 MB `Read` result rendered in full is a page nobody scrolls past.

