---
type: concept
slug: artifact-writer
title: ArtifactWriter — the run-directory writer
---
# ArtifactWriter — the run-directory writer

The class that owns the [run artifacts](../run-artifacts.md) layout end to end: locating/creating
a run directory, the fresh-start vs. resume hygiene (dropping a stale `checkpoint.json`/
`events.jsonl`), and every read/write of the files under it.

[`run_pyflow`](pyflow-driver.md) (`workhorse/workhorse/pyflow/run.py`) constructs one
writer per top-level run — fresh, or via [`resume`](#resumerun_dir---artifactwriter-classmethod) — and hands it
to the run's `RunEnv`. From there [`drive`](pyflow-driver.md) writes the
[`(state, params)` checkpoint](#write_state_checkpointstate-params--inputs-flownone-ctxnone-waiting_onnone)
before every transition, and the engine behind
[`self.call` / `self.agent` / `self.handoff`](../workflow-format.md#workflow-subclass) records each
node visit. A `handoff` gets a **nested** writer rooted under the
calling node's directory (via [`subscope`](#subscopenode_id-flow_name--resumefalse---artifactwriter)).

Four methods on this class no longer have a production caller: they served the retired YAML
front-end's node-at-a-time checkpoint and its `branch` node type. They are still on the class and
still exercised by tests, and are documented under
[Retired with the YAML engine](#retired-with-the-yaml-engine) so a reader who meets one in a test
or an old run directory can tell what it was for.

- code: `workhorse/workhorse/artifacts.py::ArtifactWriter`

## Class constants

- `CHECKPOINT_FILE` — `"checkpoint.json"`.
- `EVENTS_FILE` — `"events.jsonl"` — append-only, per-node event log; kept separate from
  `checkpoint.json` (which is overwritten every step) because it must preserve full node-visit
  history for spend/output attribution — see [`events.jsonl`](../run-artifacts.md#eventsjsonl).

## Instance state

Every constructor sets the same five attributes: `run_dir: Path`, `_started_at: str` (ISO-8601
UTC, set once and preserved across a resume), `_workflow_name: str`, `_run_id: str`, and
`_seq: int` — the monotonic checkpoint sequence. `run_id` and `started_at` are exposed as
read-only properties; `started_at` is what anchors the run's wall-clock budget
(`WORKHORSE_MAX_RUNTIME_S`) to the *original* start rather than to the latest resume.

## Constructors

Four ways to obtain a writer, covering fresh start, resume, and nested handoff scopes.

### `__init__(workflow_name, runs_dir, run_id=None)`
The top-level, fresh-run constructor.
1. If `run_id` is `None`, derive one: `<UTC timestamp %Y%m%d-%H%M%S>-<4 hex chars of a uuid4>`. A
   caller-supplied `run_id` instead gives a single stable run dir that is resumed in place across
   restarts — which is what `run_pyflow`'s `auto_resolve` always supplies (the explicit
   `--run-id`, a digest of `--params`, or `default`).
2. `run_dir = runs_dir / f"{workflow_name}-{run_id}"`; create it (`mkdir(parents=True,
   exist_ok=True)`).
3. **Fresh-start hygiene:** unlink (`missing_ok=True`) any existing `CHECKPOINT_FILE` and
   `EVENTS_FILE` in `run_dir`. A stable-id dir may be reused after its previous run already
   finished; dropping both means an interruption before this run's first checkpoint can't
   resurrect the old run on the next auto-resume, and a prior run's event log can't interleave
   with this one's.
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
   and parses — so new checkpoints continue the sequence rather than restarting it.
4. `_write_run_json(terminal=None)` — re-marks the run in-progress until it reaches a terminal
   state again, which also clears any `interrupted_at`/`error` stamp.

This constructor reads only `run.json` and the checkpoint's `seq`; it does **not** interpret the
checkpoint body. Deciding whether a checkpoint is one this engine may resume from is
[`read_resume`](pyflow-driver.md)'s job, and a checkpoint whose `engine` key is not `"pyflow"` is
refused there.

### `at(run_dir, workflow_name, run_id) -> ArtifactWriter` (classmethod)
A fresh writer rooted directly at `run_dir` (no `runs_dir/<name>-<id>` derivation). Mirrors
`__init__`'s fresh-start hygiene — creates `run_dir`, drops any stale `CHECKPOINT_FILE`/
`EVENTS_FILE`, sets `_started_at`/`_workflow_name`/`_run_id`/`_seq = 0`, and calls
`_write_run_json(terminal=None)`. Used for a handoff's nested scope (see
[`subscope`](#subscopenode_id-flow_name--resumefalse---artifactwriter)), where the run dir is a
node's own subdirectory rather than a sibling of other runs under `runs_dir`.

### `subscope(node_id, flow_name, *, resume=False) -> ArtifactWriter`
Returns the writer for a child workflow handed off at `node_id`, rooted under this run's node
directory (`<run_dir>/<node_id>/_flow`).
- Algorithm: `sub_dir = run_dir / node_id / "_flow"`; if `resume` and `(sub_dir /
  CHECKPOINT_FILE).exists()`, return `ArtifactWriter.resume(sub_dir)`; otherwise return
  `ArtifactWriter.at(sub_dir, flow_name, node_id)`.
- **The engine's `handoff` never passes `resume`**, so today every handoff starts its child scope
  clean. That is not an oversight: pyflow checkpoints the *parent* state, and re-entering that
  state re-runs the handoff from the top. The contract a state owes is
  [idempotency, not determinism](../flows/workhorse-crash-resume.md), and a child run that
  restarted cleanly is exactly what that means for a handoff.
- The `resume` parameter survives for a caller that has a genuine "are we re-entering this exact
  node after a kill?" signal. It must never be fed from "does a checkpoint happen to exist": a
  child that ran to completion also leaves a checkpoint behind, so keying on mere presence would
  make a *second* handoff at the same node fast-forward through the prior child's completion and
  silently skip it.

## Writes

### `write_state_checkpoint(state, params, *, inputs, flow=None, ctx=None, waiting_on=None)`
The resume point of a Python state machine: the state to (re-)enter and the arguments bound for
it. Written by [`drive`](pyflow-driver.md) **before** dispatching into every state, and a second
time when a state returns `Await` — with `waiting_on` set — so "blocked on a human at `<path>`" is
on disk whether or not the waiting process survives.
1. `_seq += 1`.
2. Build `data = {engine: "pyflow", workflow, run_id, flow, state, params, waiting_on, inputs,
   ctx, seq, updated_at}`.
3. Write to `checkpoint.json.tmp`, then `tmp.replace(path)` — atomic rename on the same
   filesystem, so a crash mid-write still leaves the previous checkpoint valid and complete.
4. `_append_event(node_id=state, phase="enter", waiting_on=waiting_on)`.

Three fields carry design decisions rather than data:
- `params` is a flat dict of the next state's **own named arguments** — small enough to read, and
  to edit by hand, at hour 30 of a stuck run. The retired engine's `(current_id, context)` put the
  whole ambient bag here instead.
- `inputs` and `ctx` ride along because a resume must reconstruct the instance **without** re-running
  `setup()`; `self.ctx` is written once, and a resume that called `setup()` again would write it twice.
- `engine: "pyflow"` is a fail-closed discriminator. The two engines shared a runs directory and a
  `--resume-latest`, and neither can make sense of the other's checkpoint, so a foreign one is
  [refused rather than misread](pyflow-driver.md#a-checkpoint-from-the-retired-engine-is-refused-not-misread).

### `record_node(node_id, phase, **fields)`
The public entry to the append-only event log — `_append_event` with a name callers may use.
A YAML node visit was always bracketed by a checkpoint write and a `done` marker, so the engine
needed no other way in. A Python state machine checkpoints per **state** and runs several nodes
inside one, so its per-node `enter` events need an entry point that is not a checkpoint write.
Called by the engine for each `self.call` (with `blueprint=`), each `self.agent` (with `prompt=`),
and each `self.handoff` (with `flow=`); a dry run adds a stand-in marker.

### `write_step(node_id, prompt, output, context_after, next_node=None)`
Writes the artifact group for one node visit.
1. `mkdir(run_dir / node_id, exist_ok=True)`.
2. Write `prompt.md` (plain text), `output.json` (`json.dumps(output, indent=2)`),
   `context_after.json` (`json.dumps(context_after, indent=2)`).
3. `_write_done(node_id, next_node)`.

pyflow calls it for a `self.call` (prompt = a rendered `name(args)` description), a `self.agent`
(prompt = the rendered Jinja prompt, or `(dry-run) <path>` under `--dry-run`) and a `self.handoff`
(prompt = `handoff → <ChildClass>`). It always passes `context_after={}` and `next_node=None` —
there is no ambient context to snapshot and no node-graph edge to name — so those two files are
constant in a pyflow run and only `prompt.md`/`output.json` carry information.

### `record_interrupt(node_id, error)`
Records that an operator interrupt (Ctrl-C) stopped the run while `node_id` was in flight.
1. `_append_event(node_id=node_id, phase="error", error=error)` — closes that node's `enter`
   window, which otherwise dangles exactly as a wedged node's does.
2. `_write_run_json(terminal=None, error=error)` — stamps `interrupted_at`/`error`.

Without it an interrupted run is indistinguishable on disk from a wedged one, and finding out
which required going to the backend CLI's own session transcript.

Deliberately **not** `finish()`: a non-null `terminal` reads as "this run is over" to
`auto_resolve`/`find_latest_resumable`, and an interrupted run is precisely the one that must
still auto-resume in place (see [crash and resume](../flows/workhorse-crash-resume.md)). The stamp
clears itself on the next `_write_run_json` — a `resume`, or the run finishing.

Called by `run_pyflow`'s `KeyboardInterrupt` handler, which reads the in-flight state name back
out of the checkpoint.

### `finish(terminal)`
Ends the run.
1. Write `context.json` = `"{}"` — a placeholder immediately overwritten by the caller's
   [`write_final_context`](#write_final_contextcontext); `drive` always calls
   `write_final_context` first, so this only guards a caller that doesn't.
2. `_write_run_json(terminal=terminal)`.
3. `_append_event(node_id="<run>", phase="terminal", terminal=terminal)`.

`drive` passes `"terminal"` when the entry flow returns `Done`; `run_pyflow` passes `"fail"` when a
`PyflowError` ends the run.

### `write_final_context(context)`
Writes `context.json` = `json.dumps(context, indent=2)`, called right before `finish()`. Under
pyflow this is the run's **result**, not a context bag: `drive` writes `{"result": …}` carrying
whatever the entry flow's `Done` returned.

### `_append_event(node_id, phase, **fields)` — private
Appends one line to `EVENTS_FILE`: `{ts: <now>, seq: _seq, node: node_id, phase, **fields}` as
JSON followed by `\n`. Best-effort — any `OSError` is swallowed, since instrumentation must never
crash a run. The same record is mirrored to the OTel exporter (`otel.record_event`), which is why
node spans need no other hook: root run and nested handoff scopes alike funnel through here.
Reached via `write_state_checkpoint` (`phase="enter"`), `record_node` (any phase), `_write_done`
(`phase="done"`, adding `next`), `finish` (`phase="terminal"`, adding `terminal`), and
`record_interrupt` (`phase="error"`, adding `error`).

### `_write_done(node_id, next_node)` — private
Marks `node_id` complete. `mkdir(run_dir / node_id, exist_ok=True)`; write `<node_id>/done.json` =
`{seq: _seq, next: next_node}`; then `_append_event(node_id=node_id, phase="done",
next=next_node)`. Called by `write_step` (and by the retired `write_branch`). The recorded `seq`
was how the YAML engine's fast-forward told "finished under the current checkpoint" from "stale
artifact from an earlier loop visit"; pyflow has no fast-forward — it re-enters the checkpointed
state from the top — so today the field is history rather than a resume input.

### `_write_run_json(terminal, error=None)` — private
Writes `run.json` = `{workflow: _workflow_name, run_id: _run_id, started_at: _started_at, ended_at:
<now if terminal else null>, terminal, interrupted_at: <now if error and not terminal else null>,
error, pid: os.getpid()}`. Called by every constructor (`terminal=None`), by `finish`
(`terminal="terminal"`/`"fail"`), and by `record_interrupt` (`terminal=None`, `error=<the exception
name>`). Every call rewrites the whole file, so `interrupted_at`/`error` survive only until the run
resumes or ends. The `pid` is also a telemetry resource attribute; it is recorded here so it
survives with telemetry off.

## Reads

### `read_checkpoint() -> dict | None`
Returns `CHECKPOINT_FILE`'s parsed contents, or `None` if it doesn't exist. Unlike the readers
below, a malformed `checkpoint.json` is **not** caught — `json.loads` raises straight through.
`run_pyflow` reads it to name the in-flight state when a Ctrl-C arrives.

### `read_output(node_id) -> dict | None`
Returns `<node_id>/output.json` parsed, `None` when the file is absent or unparseable, and
`{"value": data}` when the recorded payload was not a JSON object. Backs
[`self.output(node)`](../workflow-format.md#workflow-subclass) — a state reading back what an
earlier node in the same run
recorded, rather than threading the value through every transition in between. Distinguishing
"absent" from "empty" is deliberate and is the caller's to act on: `self.output` raises
`NodeNotRunError` on `None`, where the YAML template helper this replaced returned `""` for both.

### `read_events() -> list[dict]`
Reads `EVENTS_FILE` in order; `[]` if the file doesn't exist. Splits on lines, skips blank lines,
`json.loads`-parses each non-blank line and skips (rather than raising on) any line that fails to
parse. Consumers (e.g. a cost/spend scorecard) join the returned records against timestamped
provider spend and git commit history.

## Retired with the YAML engine

Still on the class, still covered by tests, **no production caller**. Listed so the methods are
identifiable when they turn up in a test or in a run directory written by the old front-end.

### `write_checkpoint(current_id, context)`
The YAML engine's checkpoint: the *node* about to run plus the whole ambient context bag, at
`{workflow, run_id, current_id, seq, context, updated_at}` — no `engine` key, which is what lets
`read_resume` recognize and refuse it. Superseded by
[`write_state_checkpoint`](#write_state_checkpointstate-params--inputs-flownone-ctxnone-waiting_onnone).

### `write_branch(node_id, path, value, next_node)`
Wrote `<node_id>/branch.json` = `{path, value, next: next_node}` for a `branch` node — routing
only, no prompt/output/context-diff — then `_write_done`. There is no `branch` node type in a
Python workflow: a branch is an ordinary `if` inside a state method, and the edge it picks is the
`Continue` that state returns.

### `read_done(node_id) -> dict | None`
Returned `<node_id>/done.json` parsed, or `None` if absent or unparseable. Fed the YAML engine's
fast-forward decision, which pyflow does not have.

### `read_context_after(node_id) -> dict | None`
Returned `<node_id>/context_after.json` parsed, or `None`, with the same error handling. Restored
the ambient context when fast-forwarding past an already-completed node. pyflow restores `ctx` from
the checkpoint instead, and writes `context_after.json` as a constant `{}`.

## Consumers

- [`run_pyflow`](pyflow-driver.md) (`workhorse/workhorse/pyflow/run.py`) — constructs the writer
  fresh or via `resume`, reads the checkpoint back on a Ctrl-C, and calls `finish("fail")` when a
  `PyflowError` ends the run.
- [`drive`](pyflow-driver.md) (`workhorse/workhorse/pyflow/driver.py`) — `write_state_checkpoint`
  before every transition and again on an `Await`, then `write_final_context` + `finish("terminal")`
  when the entry flow returns `Done`.
- the engine (`workhorse/workhorse/pyflow/engine.py`) — `record_node` +
  `write_step` per node visit, `subscope` for a handoff's nested scope, and `read_output` behind
  `self.output(node)`.
- A cost/spend scorecard (external to workhorse) — reads `events.jsonl` via `read_events`.
