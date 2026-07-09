---
type: concept
slug: artifact-writer
title: ArtifactWriter — the run-directory writer
---
# ArtifactWriter — the run-directory writer

The class that owns the [run artifacts](../run-artifacts.md) layout end to end: locating/creating
a run directory, the fresh-start vs. resume hygiene (dropping a stale `checkpoint.json`/
`events.jsonl`), and every read/write of the files under it. [`run`](../workhorse.md#run)
(`workhorse/workhorse/main.py`) constructs or resumes one writer per top-level run and one nested
writer per `flow` node (via `subscope`, below); [workflow execution](workflow.md#execution)'s
checkpoint/fast-forward/resume logic and [`workhorse.testing`](testing.md)'s `RunResult` both read
back what it writes.

- code: `workhorse/workhorse/artifacts.py::ArtifactWriter`

## Class constants

- `CHECKPOINT_FILE` — `"checkpoint.json"`.
- `EVENTS_FILE` — `"events.jsonl"` — append-only, per-node event log; kept separate from
  `checkpoint.json` (which is overwritten every step) because it must preserve full node-visit
  history for spend/output attribution — see [`events.jsonl`](../run-artifacts.md#eventsjsonl).

## Instance state

Every constructor sets the same five attributes: `run_dir: Path`, `_started_at: str` (ISO-8601
UTC, set once and preserved across a resume), `_workflow_name: str`, `_run_id: str`, and
`_seq: int` — the monotonic checkpoint sequence (see [`write_checkpoint`](#write_checkpoint)).

## Constructors

Four ways to obtain a writer, covering fresh start, resume, and nested-flow scopes.

### `__init__(workflow_name, runs_dir, run_id=None)`
The top-level, fresh-run constructor.
1. If `run_id` is `None`, derive one: `<UTC timestamp %Y%m%d-%H%M%S>-<4 hex chars of a uuid4>`. A
   caller-supplied `run_id` (e.g. `--auto`'s stable program name) instead gives a single stable run
   dir that is resumed in place across restarts.
2. `run_dir = runs_dir / f"{workflow_name}-{run_id}"`; create it (`mkdir(parents=True,
   exist_ok=True)`).
3. **Fresh-start hygiene:** unlink (`missing_ok=True`) any existing `CHECKPOINT_FILE` and
   `EVENTS_FILE` in `run_dir`. A stable-id dir may be reused after its previous run already
   finished (e.g. `--auto` restarting); dropping both means an interruption before this run's first
   checkpoint can't resurrect the old run on the next auto-resume, and a prior run's event log
   can't interleave with this one's.
4. Set `_started_at` to now, `_workflow_name`, `_run_id`, `_seq = 0`.
5. `_write_run_json(terminal=None)`.

### `resume(run_dir) -> ArtifactWriter` (classmethod)
Re-binds to an existing run directory for checkpoint resume, **without** creating a new run or
touching its step artifacts.
1. Read `run_dir / "run.json"`; on `FileNotFoundError`/`json.JSONDecodeError` fall back to `{}`.
2. `_workflow_name = meta.get("workflow", run_dir.name)`, `_run_id = meta.get("run_id",
   run_dir.name)`, `_started_at = meta.get("started_at", <now>)` — preserving the original run's
   metadata when present.
3. `_seq = 0`, then overwritten from `run_dir / CHECKPOINT_FILE`'s `"seq"` key if that file exists
   and parses — so new checkpoints continue the sequence rather than colliding with completion
   markers already on disk.
4. `_write_run_json(terminal=None)` — re-marks the run in-progress until it reaches a terminal
   state again.

### `at(run_dir, workflow_name, run_id) -> ArtifactWriter` (classmethod)
A fresh writer rooted directly at `run_dir` (no `runs_dir/<name>-<id>` derivation). Mirrors
`__init__`'s fresh-start hygiene — creates `run_dir`, drops any stale `CHECKPOINT_FILE`/
`EVENTS_FILE`, sets `_started_at`/`_workflow_name`/`_run_id`/`_seq = 0`, and calls
`_write_run_json(terminal=None)`. Used for a flow's nested scope (the fresh-entry branch of
[`subscope`](#subscope)), where the run dir is a node's own subdirectory rather than a sibling of
other runs under `runs_dir`.

### `subscope(node_id, flow_name, *, resume=False) -> ArtifactWriter`
Returns the writer for a `flow` node invoked at `node_id`, rooted under this run's node directory
(`<run_dir>/<node_id>/_flow`).
- `resume` **must** come from the engine's "are we re-entering this exact node after a kill?"
  signal — never from "does a checkpoint happen to exist". A flow that ran to completion also
  leaves a checkpoint behind, so keying resume on mere checkpoint presence would make a *second*
  invocation of the same flow node (a loop body calling a flow again) fast-forward through the
  prior run's completion and silently skip the whole flow.
- Algorithm: `sub_dir = run_dir / node_id / "_flow"`; if `resume` and `(sub_dir /
  CHECKPOINT_FILE).exists()`, return `ArtifactWriter.resume(sub_dir)`; otherwise return
  `ArtifactWriter.at(sub_dir, flow_name, node_id)` — every fresh (re-)entry starts the child clean,
  which is what lets a flow inside a loop run again each iteration.

## Writes

### `write_checkpoint(current_id, context)`
Atomically records the node about to run and the context going into it, so a crash mid-node still
leaves a valid, complete prior checkpoint.
1. `_seq += 1`.
2. Build `data = {workflow, run_id, current_id, seq: _seq, context, updated_at: <now>}`.
3. Write to `checkpoint.json.tmp`, then `tmp.replace(path)` — atomic rename on the same
   filesystem.
4. `_append_event(node_id=current_id, phase="enter")` — mirrors the node-entry to the event log.

### `write_step(node_id, prompt, output, context_after, next_node=None)`
Writes the artifact group for an `agent`/`script`/`call`/`flow` node.
1. `mkdir(run_dir / node_id, exist_ok=True)`.
2. Write `prompt.md` (plain text), `output.json` (`json.dumps(output, indent=2)`),
   `context_after.json` (`json.dumps(context_after, indent=2)`).
3. `_write_done(node_id, next_node)`.

### `write_branch(node_id, path, value, next_node)`
Writes the artifact for a `branch` node — routing only, no prompt/output/context-diff.
1. `mkdir(run_dir / node_id, exist_ok=True)`.
2. Write `branch.json` = `{path, value, next: next_node}`.
3. `_write_done(node_id, next_node)`.

### `finish(terminal)`
Ends the run.
1. Write `context.json` = `"{}"` — a placeholder immediately overwritten by the caller's
   [`write_final_context`](#write_final_context); callers (`run()`, `_run_flow`) always call
   `write_final_context` first, so this only guards a caller that doesn't.
2. `_write_run_json(terminal=terminal)`.
3. `_append_event(node_id="<run>", phase="terminal", terminal=terminal)`.

### `write_final_context(context)`
Writes `context.json` = `json.dumps(context, indent=2)` — the final `WorkflowContext` snapshot,
called right before `finish()`.

### `_append_event(node_id, phase, **fields)` — private
Appends one line to `EVENTS_FILE`: `{ts: <now>, seq: _seq, node: node_id, phase, **fields}` as
JSON followed by `\n`. Best-effort — any `OSError` is swallowed, since instrumentation must never
crash a run. Called by `write_checkpoint` (`phase="enter"`), `_write_done` (`phase="done"`, adding
`next`), and `finish` (`phase="terminal"`, adding `terminal`).

### `_write_done(node_id, next_node)` — private
Marks `node_id` complete under the current checkpoint `_seq`. `mkdir(run_dir / node_id,
exist_ok=True)`; write `<node_id>/done.json` = `{seq: _seq, next: next_node}`; then
`_append_event(node_id=node_id, phase="done", next=next_node)`. Called by `write_step` and
`write_branch`. Recording the seq a node ran under is what lets resume distinguish "this node
finished under the current checkpoint" (fast-forward past it) from "stale artifact from an earlier
loop visit" (must re-run) — see [workflow execution](workflow.md#execution).

### `_write_run_json(terminal)` — private
Writes `run.json` = `{workflow: _workflow_name, run_id: _run_id, started_at: _started_at, ended_at:
<now if terminal else null>, terminal}`. Called by every constructor (`terminal=None`) and by
`finish` (`terminal=<the terminal node's type>`).

## Reads

### `read_checkpoint() -> dict | None`
Returns `CHECKPOINT_FILE`'s parsed contents, or `None` if it doesn't exist. Unlike the readers
below, a malformed `checkpoint.json` is **not** caught — `json.loads` raises straight through.

### `read_done(node_id) -> dict | None`
Returns `<node_id>/done.json`'s parsed contents, or `None` if the file is absent or fails to parse
(`json.JSONDecodeError` caught).

### `read_context_after(node_id) -> dict | None`
Returns `<node_id>/context_after.json`'s parsed contents, or `None` if absent or invalid, same
error handling as `read_done`.

### `read_events() -> list[dict]`
Reads `EVENTS_FILE` in order; `[]` if the file doesn't exist. Splits on lines, skips blank lines,
`json.loads`-parses each non-blank line and skips (rather than raising on) any line that fails to
parse. Consumers (e.g. a cost/spend scorecard) join the returned records against timestamped
provider spend and git commit history.

## Consumers

- [`run`](../workhorse.md#run) (`workhorse/workhorse/main.py::run`) — constructs `ArtifactWriter`
  fresh or via `resume`, and drives `write_checkpoint`/`write_step`/`write_branch`/
  `write_final_context`/`finish` across the [workflow execution](workflow.md#execution) loop;
  `_run_flow` calls `subscope` to obtain a nested writer for a `flow` node, and `_should_fast_forward`
  compares a node's `read_done` seq against the current checkpoint's seq to decide whether to
  re-run it.
- [`workhorse.testing`](testing.md)'s `RunResult` — reads back `context.json`, `checkpoint.json`,
  `<node-id>/output.json`, and `<node-id>/prompt.md` to make assertions about a completed test run.
- A cost/spend scorecard (external to workhorse) — reads `events.jsonl` via `read_events`.
