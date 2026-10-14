# Live transcript in the run pane

## 1. Problem

An operator who opens a running workflow in groom sees spans, logs and metric cells. Those say
that a turn is running and for how long. They do not say what the agent is doing: which files
it reads, which commands it runs, what it concluded. The answer exists in the agent's own
output, and workhorse reads that output line by line. Nothing carries it to groom while the
turn runs.

Workhorse drives five CLIs: Claude Code, Codex, Cline, Copilot and OpenCode. Each prints a
different JSON vocabulary. Groom must render one shape for all five.

**Done**, as the operator sees it: they open a live run of any of the five harnesses in groom.
In the same timeline as the spans and logs, they read the turn's prompt, each agent message,
each reasoning block the CLI emits, and each tool call with its input, its result and whether
it failed. A new entry appears within a few seconds of the CLI printing it. A finished turn
keeps its transcript in the same shape.

## 2. Decisions

- **The format is ACP's `session/update`.** Each transcript line is the `params` object of an
  ACP `session/update` notification: `sessionId`, `update`, and `_meta`. `_meta` is ACP's
  extension slot. It carries `ts`, `node` and, for a subagent's events, `parent` (the tool
  call that spawned it). A backend that later runs over ACP writes its notifications to the
  same file with `_meta` added, and groom needs no change.
- **The backends keep running the CLIs as they do now.** Each one gains a mapper from its own
  event vocabulary to ACP updates. Resume, compaction, tool allow-lists, the Codex guard and
  usage stay where they are.
- **The mapper is a pure function per backend.** It takes one parsed event and returns zero or
  more ACP updates. It lives in the backend's module beside the vocabulary it reads, and the
  agent-backend port exposes it. The null backend returns nothing.
- **One writer sees every line.** The per-line closure in `runner/process.py` already sees
  every redacted line of every backend, before the backend's own parser. The writer parses
  the line again and hands the event to the backend's mapper. A second JSON parse per line
  costs less than threading a writer through five parsers.
- **The live file is written on every turn.** It does not depend on whether the CLI keeps its
  own session store, unlike the existing raw tee.
- **The transcript joins the pane's existing timeline.** It is a fourth kind beside spans, logs
  and metrics in `LiveHistory`, and it travels in the same `detail` frames. The pane gets no
  second channel and no second socket.

## 3. The line format

```json
{"sessionId": "…", "update": {"sessionUpdate": "tool_call", "toolCallId": "toolu_01", "title": "Read groom/app.py", "kind": "read", "status": "in_progress", "rawInput": {"file_path": "groom/app.py"}}, "_meta": {"ts": 1760440000.123, "node": "implement"}}
```

The updates a mapper emits:

| Update                | From                                                        |
| --------------------- | ----------------------------------------------------------- |
| `user_message_chunk`  | the turn's prompt, written by workhorse when the turn opens |
| `agent_message_chunk` | an assistant text block or message item                     |
| `agent_thought_chunk` | a reasoning or thinking block, when the CLI emits one       |
| `tool_call`           | a tool invocation: id, title, kind, status, raw input       |
| `tool_call_update`    | the same id with its result content and its final status    |
| `plan`                | a todo-list tool call or item, as ACP plan entries          |

An edit tool call carries an ACP `diff` content block when the CLI's event holds the old and
new text, and a `locations` entry with the path otherwise.

`sessionId` is empty until the CLI names its session. Claude and Codex name it in their first
event. Groom keys entries by the file they came from, so an empty id breaks nothing.

## 4. The pieces

### workhorse

- `runner/transcript.py` gains the live writer. It opens
  `<run_dir>/transcripts/live/<slug>.jsonl` when the turn begins and writes the prompt as
  the first update. It appends each mapped update and flushes after each line, so a reader
  sees it at once. It reuses the tee's byte cap and truncation marker.
- `capture` renames the live file to `<slug>__<session_id>.acp.jsonl`, beside the turn's other
  transcript files, so the archive harvest picks it up with its turn. A turn that never
  reaches capture leaves its file in `live/`, where groom still reads it.
- Each backend module gains its mapper. `AgentBackend` exposes it.
- The `agent_turn` span gets the visit attributes `VisitKey.attributes()` already defines. That
  method has no caller today. With it, groom can place a transcript under the turn span it
  belongs to, by slug, instead of by timestamp alone.

### groom

- `LiveHistory` gains transcript entries. A `tool_call_update` merges into its `tool_call` by
  `toolCallId`, the way a re-delivered span merges by `span_id`. Transcript entries have their
  own trim limit, so a chatty turn cannot push spans out of the window.
- `LiveHistory` keeps a read offset per live file.
- **Native runs:** on each live tick, groom reads each watched run's live files from their
  offsets through `localfs`. The tick is 5 seconds today.
- **Container runs:** the sidecar already announces a `turn` frame for any write under
  `transcripts/`. For a watched run, the host reads from the offset with the existing
  `readTurnFile` byte-range RPC. The watch backend batches changes over about 1.6 seconds.
  Unwatched runs are skipped. Their transcript reaches the archive at capture.
- **Seeding:** when a tab starts watching a run, groom reads the newest two live or captured
  ACP files from offset 0.
- `projection.history_lines` renders the transcript kind. The `Detail` pane's trail shows the
  entries inline with the spans, reusing the attendant view's message and tool components. A
  filter switches between everything, transcript only and telemetry only.

## 5. Slices

Each slice runs end to end in groom.

1. **Claude, native run.** Claude's mapper, the live writer, the native tail, the history kind
   and the pane rendering. An operator opens a native Claude run and watches its prompt,
   messages, tool calls and results appear beside the spans within one tick.
2. **Container runs.** The sidecar path and the offset reads. The same view works for a run
   inside docker.
3. **Codex.** Its mapper. Codex's `exec --json` names `agent_message`, `reasoning`,
   `command_execution`, `file_change`, `mcp_tool_call`, `web_search` and `todo_list` items,
   with `item.started` and `item.completed`. The backend reads only `agent_message` today.
4. **OpenCode, Copilot and Cline.** One mapper each. Their backends parse the answer text and
   usage only, so the vocabulary for tool calls and reasoning is unknown here. Each mapper
   starts by recording a real turn. Turns of these three already leave a raw
   `<stem>.tee.jsonl` in the run directory, because none of them has a store workhorse copies.
   Those files are the fixtures.
5. **Turn grouping.** The visit attributes on the `agent_turn` span, and the pane nesting each
   transcript under its turn.

## 6. Check first

- **The archive pull may re-read on every write.** Every write under `transcripts/` already
  triggers a `turn` frame and an archive pull. The live file writes far more often than the
  tee did. Check whether `sidecar_turns.schedule` coalesces pulls. If it does not, exclude
  `live/` from the archive pull.
- **Claude's tool results.** The plan assumes Claude's stream-json carries each tool result as
  a `user` event with a `tool_result` block, and each subagent's events with a parent tool id.
  Confirm both on one recorded turn before writing the mapper.
- **Codex file changes.** `file_change` items may name paths without the text. If so, Codex
  edits show a location and no diff.
- **Prompt size.** Book prompts are large. The pane shows the prompt collapsed, and the byte
  cap covers the file.

## 7. Found while mapping, not in scope

- **Secrets reach the transcript unredacted.** The per-line redactor runs with an empty secret
  list, because no backend passes one. The live file inherits that. The CLI's own session
  store is equally unredacted, and groom is local, so the plan does not make this worse. It
  does put the output on a screen.
- **Failed turns leak their raw tee.** `.pending/<slug>.jsonl` is deleted only inside
  `capture`. A turn that times out or exits non-zero leaves it behind.
- **Stale comments.** `groom/groom/assets/dashboard.js` names a `GET /worker/{id}/live` route
  in two comments. The route is `GET /worker/{id}`.
