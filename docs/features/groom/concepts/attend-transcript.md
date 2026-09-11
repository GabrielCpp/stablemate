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
- does: otherwise, call [copy_session](#method-copy_session) to copy the transcript from the CLI store, then call `has_body()` again and return its result
- verify: json_path(path="result", equals=true)
- returns: `True` if the transcript is present after copying, `False` if the copy did not produce any transcript data
- verify: json_path(path="result", equals=true)
- code: `groom/groom/attend_transcript.py::ensure_body`
- detail: [copy_session](#method-copy_session)

Called by the attendant pane API before rendering; retries the copy exactly once if it did not happen at exit time.

### method: attend_root
- sig: `() -> Path`
- does: resolve the path by joining `turns.transcripts_root()` with the module-level constant `ATTEND_DIR` ("attend"); the filesystem is not touched (no `mkdir`, no `stat`, no read)
- verify: json_path(path="result", matches=".*/transcripts/attend$")
- returns: a `pathlib.Path` to `<groom data dir>/transcripts/attend`; the directory may or may not exist on disk at the moment of the call — this method does not create it
- verify: json_path(path="result", matches=".*/transcripts/attend$")
- persistence: attend-root — names the persistent storage location for attendant session transcripts (see the module intro); the directory sits beside the run-major tree so an attendant record outlives its run
- verify: json_path(path="result", matches=".*/transcripts/attend$")
- code: `groom/groom/attend_transcript.py::attend_root`

This is the canonical reference for the on-disk location. The only in-tree caller is [session_dir](#method-session_dir); everything else goes through `session_dir(session_id)`. Exposed publicly so an operator can shell into the directory without first asking groom for a session id.

### method: session_dir
- sig: `(session_id: str) -> Path`
- does: return `attend_root() / session_id` — paths are joined without filesystem touch (no `mkdir`, no `stat`, no read)
- verify: json_path(path="result", matches=".*/transcripts/attend/.+$")
- returns: a `pathlib.Path` whose string form ends in `/transcripts/attend/<session_id>`
- verify: json_path(path="result", matches=".*/transcripts/attend/.+$")
- returns: the directory may or may not exist on disk at the moment of the call — this method does not create or stat it
- verify: json_path(path="result", matches=".*/transcripts/attend/.+$")
- raises: nothing — path joining never touches the filesystem, so no `OSError` is possible
- verify: json_path(path="exception.type", absent=true)
- consistency: session-dir — the session directory is `<attend_root()>/<session_id>`, so a session's directory is always addressable from its id alone
- verify: json_path(path="result", matches=".*/transcripts/attend/.+$")
- code: `groom/groom/attend_transcript.py::session_dir`
- tests: `groom/tests/test_attend.py::test_a_session_with_nothing_copied_renders_empty_rather_than_raising`

The only direct exercise of this method by name is the `path` field of the empty-render result, which pins the resolved directory under any input. The renderer's other test case, `test_a_session_reads_back_as_a_conversation`, goes through `session_dir` indirectly via the `_transcript` helper that lays down a fake session before calling `render_session`.

## Methods

The methods that turn a stored transcript into the readable prose the dashboard pane
displays. Tool calls are collapsed to one line (their subject), full JSON is converted to
prose, and thinking tokens are dropped.

### method: render_session
- sig: `(session_id: str) -> dict[str, Any]`
- abstract: false
- does: resolve the session directory via [session_dir](#method-session_dir) and read `<session_dir>/<session_id>.jsonl` through [_entries](#method-_entries) when that file exists on disk
- verify: json_path(path="result.entries", matches=".+")
- does: leave the main entries list empty when the main JSONL is missing or unreadable, rather than raising
- verify: json_path(path="result.entries", matches="^\\[\\]$")
- does: walk `<session_dir>/<session_id>/` recursively for every `.jsonl` when that subdirectory exists, in sorted path order
- verify: json_path(path="result.entries", matches="kind")
- does: for each sidechain file that yields entries, prepend a divider dict of `{"kind": "divider", "label": "subagent · <stem>"}` where `<stem>` is the JSONL filename without extension, before appending the parsed entries
- verify: created(subject="divider entries before sidechain content")
- does: skip a sidechain file that parses to no entries without emitting a divider
- verify: json_path(path="result.entries", matches="divider")
- raises: nothing — [_entries](#method-_entries) handles a missing or unreadable file by returning `[]`, and the renderer tolerates missing main/sidechains paths without surfacing an exception
- verify: json_path(path="exception.type", absent=true)
- returns: a dict whose `session_id` is the verbatim input string
- verify: json_path(path="result.session_id", equals="sess-1")
- returns: a dict whose `present` is `true` iff the entries list is non-empty, `false` otherwise (no transcript data found)
- verify: json_path(path="result.present", equals=false)
- returns: a dict whose `path` is the string form of [session_dir](#method-session_dir), emitted regardless of whether any transcripts were read
- verify: json_path(path="result.path", matches=".*/transcripts/attend/[^/]+$")
- returns: a dict whose `entries` is the ordered list of rendered entries — main first, then each sidechain block preceded by its divider
- verify: json_path(path="result.entries", matches="kind")
- code: `groom/groom/attend_transcript.py::render_session`
- detail: [Parsed entries](#parsed-entries)
- tests: `groom/tests/test_attend.py::test_a_session_reads_back_as_a_conversation`
- tests: `groom/tests/test_attend.py::test_a_session_with_nothing_copied_renders_empty_rather_than_raising`

Called by the `GET /api/attend/sessions/{session_id}` handler in [`groom/groom/app.py`](../../../groom/groom/app.py) (registered as `attend_session`, called via `asyncio.to_thread`) — the single function the dashboard pane reaches through that endpoint, the one that decides what the operator reads.

### method: _entries
- sig: `(path: Path, sidechain: bool = False) -> list[dict[str, Any]]`
- does: read the file at `path` with `errors="replace"`, so a decode error in any byte does not abort the read
- verify: json_path(path="exception.type", absent=true)
- does: return an empty list when the file cannot be opened (catches `OSError`)
- verify: count(subject="result", equals=0)
- does: skip a line silently when `json.loads(line)` raises `ValueError`
- verify: json_path(path="exception.type", absent=true)
- does: skip a record silently whose parsed JSON is not a dict
- verify: json_path(path="exception.type", absent=true)
- does: skip a record silently whose `message` field is not a dict
- verify: json_path(path="exception.type", absent=true)
- does: skip a line that is empty after stripping whitespace
- verify: json_path(path="exception.type", absent=true)
- does: derive the role from `message.role`, falling back to `record.type`, then to the empty string
- verify: json_path(path="result[?(@.kind=='message')].role", matches="^(assistant|user|)$")
- does: emit one `message` entry per line whose `_text_of(content)` is non-empty, carrying `kind`, `role`, `text`, `sidechain`
- verify: json_path(path="result[?(@.kind=='message')]", matches="text")
- does: emit one `tool` entry per `tool_use` block on a non-result line, with `name` defaulting to literal `"tool"` when the block omits `name`, `summary` from `_tool_summary(name, args)`, `detail` from [_detail_of](#method-_detail_of), `result=""`, `failed=false`, `sidechain`
- verify: json_path(path="result[?(@.kind=='tool' && @.result=='')]", matches="summary")
- does: track each emitted tool call in `pending[block.id]` so a later `tool_result` block on a later line can pair back to it
- verify: json_path(path="result[?(@.kind=='tool')]", matches="name")
- does: pair each `tool_result` block back to its pending tool call by `tool_use_id`, setting the call's `result` field from [_result_text](#method-_result_text) and `failed` from `block.is_error`
- verify: json_path(path="result[?(@.kind=='tool' && @.result!='')]", matches="failed")
- does: emit a standalone `tool` entry for a `tool_result` block whose `tool_use_id` has no matching pending call — `name="result"`, `summary="result"`, `detail=""`, `result` from [_result_text](#method-_result_text), `failed` from `block.is_error`
- verify: json_path(path="result[?(@.kind=='tool' && @.name=='result')].summary", equals="result")
- does: skip message and tool_use extraction on any line that yielded at least one `tool_result` block, so a result-bearing line produces only the tool-result entries (paired or orphan) and no new message or fresh tool_use entry
- verify: count(subject="message entries produced on a tool_result-bearing line", equals=0)
- does: propagate the input `sidechain` flag verbatim onto every emitted entry
- verify: json_path(path="result[*].sidechain", matches="^(true|false)$")
- raises: nothing — file read failures return `[]`, JSON parse failures skip the line, and absent fields fall back to empty defaults rather than propagating
- verify: json_path(path="exception.type", absent=true)
- returns: an ordered list of `dict[str, Any]` entries — message and tool entries interleaved by JSONL record order, with each tool call's `result` field backfilled by the matching tool_result block on the same or a later line
- verify: json_path(path="result", matches="^\\[")
- code: `groom/groom/attend_transcript.py::_entries`
- detail: [_detail_of](#method-_detail_of)
- detail: [_result_text](#method-_result_text)
- detail: [_text_of](#method-_text_of)
- detail: [_tool_summary](#method-_tool_summary)

### method: _tool_summary
- sig: `(name: str, args: Any) -> str`
- does: if `args` is not a dict (a string, list, `None`, or any non-mapping value), return `name` unchanged without iterating
- verify: json_path(path="result", equals="Read")
- does: for `args` that is a dict, check `file_path`, `path`, `command`, `pattern`, `query`, `url`, `prompt` in that order and, for the first one holding a non-empty string, return `name: <first line of that value, truncated to 160 chars>`
- verify: json_path(path="result", equals="Read: /tmp/x")
- does: for `args` that is a dict but holds no non-empty string at any of those keys, return the tool name alone
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

### method: _result_text
- sig: `(content: Any) -> str`
- does: when `content` is a string, return it truncated to `MAX_DETAIL_CHARS`
- verify: json_path(path="result", matches="^.{0,4000}$")
- does: when `content` is a list, extract text from each block with `type == "text"` (joined with `\n`), drop non-text blocks, then truncate the join to `MAX_DETAIL_CHARS`
- verify: json_path(path="result", matches="^.{0,4000}$")
- does: when `content` is anything else, return the empty string
- verify: json_path(path="result", equals="")
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

Three module-level constants govern the renderer's behavior, bound at import time and read by every public function:

### field: ATTEND_DIR

- type: string — a single path segment
- default: `"attend"`
- required: true
- semantics: trailing segment of the attendant transcript root, appended to `turns.transcripts_root()` by [attend_root](#method-attend_root) to produce `<groom data dir>/transcripts/attend`
- semantics: keeps the attendee tree in a flat sibling of the run-major `transcripts/<run_id>/` tree, so an attendant record outlives the run it described — the run-major tree is renamed whole to `archives/<run_id>/` when a run is frozen and would otherwise sweep the attend record away with it
- code: `groom/groom/attend_transcript.py::ATTEND_DIR`
- verify: json_path(path="result", equals="attend")

### field: MAX_SESSION_BYTES

- type: int — byte count
- default: `turns.MAX_RECORD_BYTES` — itself `64 * 1024 * 1024` (64 MiB) with `GROOM_TRANSCRIPT_MAX_BYTES` unset, the same per-record cap the archive imposes on run-major transcripts
- required: true
- semantics: ceiling on the bytes copied per session by [copy_session](#method-copy_session)
- semantics: the copy proceeds up to this cap and is not aborted when reached, so a session over the limit is a poorer copy rather than a missing one
- semantics: matches the run-major archive's own per-record cap so the attendee tree never exceeds the storage budget the archive sets for one run
- code: `groom/groom/attend_transcript.py::MAX_SESSION_BYTES`
- verify: json_path(path="result", equals=67108864)

### field: MAX_DETAIL_CHARS

- type: int — character count
- default: `4000`
- required: true
- semantics: truncation cap applied by [_detail_of](#method-_detail_of) to the prose rendered for one tool call's arguments — `args[:MAX_DETAIL_CHARS]` for a string argument, `"\n".join(lines)[:MAX_DETAIL_CHARS]` for a dict
- semantics: truncation cap applied by [_result_text](#method-_result_text) to the prose rendered for one tool result body — `content[:MAX_DETAIL_CHARS]` for a string, `"\n".join(parts)[:MAX_DETAIL_CHARS]` for a list of text blocks
- semantics: 4000 characters is chosen so a 2 MB `Read` result rendered in full is a page nobody scrolls past
- code: `groom/groom/attend_transcript.py::MAX_DETAIL_CHARS`
- verify: json_path(path="result", equals=4000)

## Rendering

The output contract of the renderer — what [render_session](#method-render_session) hands the dashboard pane and the per-entry shape the pane iterates over. Distinct from [## Methods](#methods), which describes the functions that produce it, and from [## Configuration](#configuration), which bounds it.

[render_session](#method-render_session) returns a dict with four fields:

- `session_id` — the session id passed in, verbatim.
- `present` — `true` iff the entries list is non-empty; `false` when no transcript data was found or copied.
- `path` — the string form of [session_dir](#method-session_dir), returned regardless of whether any transcripts were read.
- `entries` — the ordered list of rendered entries; see [Parsed entries](#parsed-entries) for the per-entry shape.

The pane iterates three entry kinds:

- `message` — a text message from assistant or user; fields `kind`, `role`, `text`, `sidechain`. Renders as the role and the joined text.
- `tool` — a tool call or its result; fields `kind`, `name`, `summary`, `detail`, `result`, `failed`, `sidechain`. Renders collapsed: the summary line above, the detail and result below. Tool results pair back to their calls by `tool_use_id`.
- `divider` — a separator between sidechains; fields `kind`, `label`. Renders as a heading-like separator with the subagent label.

Tool calls render collapsed to one line (the call subject), full JSON arguments are converted to prose (`key: value` per line), and thinking tokens are dropped from the prose view. Orphaned results — a tool result with no matching call — appear as standalone `tool` entries with `name="result"`. Sidechain entries are flagged via the `sidechain` field rather than placed in a nested structure: the divider marks the boundary, the entries follow in order.

- code: `groom/groom/attend_transcript.py::render_session`
- tests: `groom/tests/test_attend.py::test_a_session_reads_back_as_a_conversation`
- tests: `groom/tests/test_attend.py::test_a_session_with_nothing_copied_renders_empty_rather_than_raising`

## Parsed entries

The shape of one rendered transcript entry — a tagged union over the `kind` field, emitted by [_entries](#method-_entries). The renderer produces one of three union members per JSONL record, and the dashboard pane iterates them in order. Tool calls are rendered collapsed and tool results are paired back to their calls by `tool_use_id`; orphaned results (a result without a matching call) appear as standalone `tool` entries with `name="result"`. Text is extracted from message content blocks and joined; all other content types (images, code blocks, thinking, etc.) are dropped from the prose view. The per-field contract of each union member is documented under its own `### field:` heading below; the renderer is the single producer, [render_session](#method-render_session) the single assembler, and the dashboard pane the single consumer.

### field: kind

- type: string — one of `message`, `tool`, or `divider`
- required: true
- semantics: discriminator over the union member — one of `message`, `tool`, or `divider`
- semantics: emitted by the renderer on every entry
- semantics: read first by the pane to choose its rendering path
- verify: json_path(path="result.entries[*].kind", matches="^(message|tool|divider)$")
- code: `groom/groom/attend_transcript.py::_entries`

### field: role

- type: string
- required: true (when `kind == "message"`)
- semantics: speaker role, one of `assistant` or `user`
- semantics: copied verbatim from `message.role`
- semantics: present only when `kind == "message"`
- verify: json_path(path="result.entries[?(@.kind=='message')].role", matches="^(assistant|user)$")
- code: `groom/groom/attend_transcript.py::_entries`

### field: text

- type: string
- required: true (when `kind == "message"`)
- semantics: text content blocks joined with blank lines via [_text_of](#method-_text_of)
- semantics: thinking and other non-text block types are dropped
- semantics: an empty body yields no message entry
- verify: json_path(path="result.entries[?(@.kind=='message')].text", matches=".*")
- code: `groom/groom/attend_transcript.py::_text_of`

### field: name

- type: string
- required: true (when `kind == "tool"`)
- semantics: tool name, e.g., `Read` or `Bash`
- semantics: defaults to the literal `"tool"` when the record omits `name`
- semantics: fixed literal `"result"` for orphaned tool results
- verify: json_path(path="result.entries[?(@.kind=='tool')].name", matches="^\\w+$")
- code: `groom/groom/attend_transcript.py::_entries`

### field: summary

- type: string
- required: true (when `kind == "tool"`)
- semantics: one-line identifying the call subject
- semantics: computed by [_tool_summary](#method-_tool_summary) as the tool name followed by the first non-empty argument value
- semantics: argument precedence — `file_path`, `path`, `command`, `pattern`, `query`, `url`, `prompt` (first non-empty wins)
- semantics: truncated to 160 characters
- verify: json_path(path="result.entries[?(@.kind=='tool')].summary", matches="^.{0,200}$")
- code: `groom/groom/attend_transcript.py::_tool_summary`

### field: detail

- type: string
- required: true (when `kind == "tool"`)
- semantics: call arguments rendered as prose by [_detail_of](#method-_detail_of)
- semantics: one `key: value` per line, with non-string values JSON-encoded
- semantics: truncated to `MAX_DETAIL_CHARS` (4000)
- semantics: empty string when arguments are absent or not a dict
- verify: json_path(path="result.entries[?(@.kind=='tool')].detail", matches="^.{0,4000}$")
- code: `groom/groom/attend_transcript.py::_detail_of`

### field: result

- type: string
- required: true (when `kind == "tool"`)
- semantics: tool result text paired back from the matching `tool_use_id` block
- semantics: computed by [_result_text](#method-_result_text) — text content joined with newlines
- semantics: truncated to `MAX_DETAIL_CHARS` (4000)
- semantics: empty string until the matching tool-result block arrives
- verify: json_path(path="result.entries[?(@.kind=='tool')].result", matches="^.{0,4000}$")
- code: `groom/groom/attend_transcript.py::_result_text`

### field: failed

- type: bool
- required: true (when `kind == "tool"`)
- semantics: `true` iff the paired tool-result block was marked `is_error`
- semantics: defaults to `false` for a tool call whose result has not arrived
- semantics: `true` for an orphaned tool result whose block carried `is_error`
- verify: json_path(path="result.entries[?(@.kind=='tool')].failed", matches="^(true|false)$")
- code: `groom/groom/attend_transcript.py::_entries`

### field: sidechain

- type: bool
- required: true
- semantics: `true` if the entry came from a subagent sidechain file
- semantics: `false` for entries from the main `<session>.jsonl`
- semantics: divider entries also carry this flag, propagated from the sidechain block they precede
- verify: json_path(path="result.entries[*].sidechain", matches="^(true|false)$")
- code: `groom/groom/attend_transcript.py::_entries`

### field: label

- type: string
- required: true (when `kind == "divider"`)
- semantics: the subagent label, formatted as `subagent · <stem>`
- semantics: `<stem>` is the JSONL filename without its `.jsonl` extension (e.g., `subagent · sub` for `sub.jsonl`)
- semantics: present only when `kind == "divider"`, between sidechain blocks
- verify: json_path(path="result.entries[?(@.kind=='divider')].label", matches="^subagent · .+$")
- code: `groom/groom/attend_transcript.py::render_session`

