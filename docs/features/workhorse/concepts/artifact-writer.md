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
writer per top-level run — fresh, or via [`resume`](#resume) — and hands it
to the run's `RunEnv`. From there [`drive`](pyflow-driver.md) writes the
[`(state, params)` checkpoint](#write_state_checkpoint)
before every transition, and the engine behind
[`self.call` / `self.agent` / `self.handoff`](../workflow-format.md#workflow-subclass) records each
node visit. A `handoff` gets a **nested** writer rooted under the
calling node's directory (via [`subscope`](#subscope)).

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
- `TURNS_DIR` — `"turns"` — the per-visit archive whose child names come from
  [`VisitKey`](visit-key.md).

## Instance state

Every constructor sets the same nine attributes: `run_dir: Path`; `_turns_root: Path` — where
the per-visit archive actually lives (a flow's nested scope reuses the parent run's root, so
its child writer cannot empty prior visits — see [`subscope`](#subscope));
`_started_at: str` (ISO-8601 UTC, set once and preserved across a resume); `_workflow_name:
str`; `_run_id: str`; `_seq: int` — the monotonic checkpoint sequence; `_repo_start:
RepoObservation | None` — the working tree observed at the first process of the run, or
restored from `run.json` on a resume; `_profile: str` and `_profile_config: dict` — what
[`record_profile`](#record_profile) later carries to `run.json`; and `_previous_process_died_at:
str | None` plus `_previous_process_pid: int | None` — set by [`resume`](#resume) when the
prior attempt's pid is no longer alive, sticky through the rest of this run, cleared by
[`finish`](#finish). `run_id` and `started_at` are exposed as read-only properties;
`started_at` is what anchors the run's wall-clock budget (`WORKHORSE_MAX_RUNTIME_S`) to the
*original* start rather than to the latest resume.

## Constructors

Four ways to obtain a writer, covering fresh start, resume, and nested handoff scopes.

### `__init__`
`__init__(workflow_name, runs_dir, run_id=None)`
The top-level, fresh-run constructor.
- consistency: run-id — if `run_id` is `None`, derive it as `<UTC timestamp %Y%m%d-%H%M%S>-<4 hex chars of a uuid4>`

A caller-supplied `run_id` instead gives a single stable run dir that is resumed in place across
restarts — which is what `run_pyflow`'s `auto_resolve` always supplies (the explicit
`--run-id`, a digest of `--params`, or `default`). The constructor then:

1. Sets `run_dir = runs_dir / f"{workflow_name}-{run_id}"`; create it (`mkdir(parents=True,
   exist_ok=True)`).
2. **Fresh-start hygiene:** if `run_dir` exists, try `shutil.rmtree` to clear any leftover
   state from a previous run (per-node subdirectories left by the prior run would otherwise
   be misattributed to this one — a fresh-start directory must look as if no prior run ever
   landed here); on `OSError` (a busy filesystem — e.g. another process holding the tree),
   fall back to unlinking only `CHECKPOINT_FILE` and `EVENTS_FILE`. A stable-id dir may be
   reused after its previous run already finished; either path means an interruption before
   this run's first checkpoint can't resurrect the old run on the next auto-resume, and a
   prior run's event log can't interleave seq numbering with this one's. Housekeeping is
   never allowed to end a run that would otherwise work.
3. Sets `_started_at` to now, `_workflow_name`, `_run_id`, `_seq = 0`, and the visit-archive
   bookkeeping — `_turns_root = self.run_dir` (a top-level run's archive lives inside its
   own dir; [`subscope`](#subscope) rebinds this on the *child*), `_repo_start` from
   `_observe_repo()`, `_profile = ""`, `_profile_config = {}`, `_previous_process_died_at
   = None`, `_previous_process_pid = None` (a fresh run has no prior attempt to detect).
4. Calls `_write_run_json(terminal=None)`.

- code: `workhorse/workhorse/artifacts.py::_clear_stale_run`
- code: `workhorse/tests/test_artifacts_fresh.py::test_an_unremovable_run_dir_costs_the_wipe_but_not_the_run`
- tests: `workhorse/tests/test_artifacts_fresh.py::test_a_fresh_run_does_not_inherit_the_previous_runs_node_output`, `workhorse/tests/test_artifacts_fresh.py::test_a_resume_keeps_everything_the_run_had_already_written`

### `resume`
`resume(run_dir) -> ArtifactWriter` (classmethod)
Re-binds to an existing run directory for checkpoint resume, **without** creating a new run or
touching its step artifacts.
1. Read `run_dir / "run.json"`; on `FileNotFoundError`/`ValidationError` (a malformed file
   reports as `ValidationError` from `parse_run_record`) fall back to a default `RunRecord()`.
2. `_workflow_name = record.workflow or run_dir.name`, `_run_id = record.run_id or
   run_dir.name`, `_started_at = record.started_at or <now>` — preserving the original run's
   metadata when present.
3. `_seq = 0`, then overwritten from `run_dir / CHECKPOINT_FILE`'s `"seq"` key if that file
   exists and parses — so new checkpoints continue the sequence rather than restarting it.
4. Restore the carried state: `_repo_start = record.repo_start or _observe_repo()` (so the
   resume does not re-observe *now's* tree and silently overwrite what the prior process
   saw), `_profile = record.profile`, `_profile_config = dict(record.profile_config)` (a
   resume inherits the run's profile unless it states a new one via `record_profile`).
5. **Previous-process-death stamp.** When the loaded `record` has `terminal is None` *and*
   `pid is not None` *and* `_process_alive(record.pid)` is false, set
   `_previous_process_died_at = <now>` and `_previous_process_pid = record.pid`. The stamp
   is sticky through the rest of this run (it survives `_write_run_json` and every
   checkpoint write) and is what lets groom keep the run visible as something other than a
   run that has been in flight for hours with no heartbeats — a SIGKILL / OOM kill / host
   power loss cannot report its own death, so the directory has to carry the fact itself.
6. `_write_run_json(terminal=None)` — re-marks the run in-progress until it reaches a
   terminal state again, which also clears any `interrupted_at`/`error` stamp.

This constructor reads only `run.json` and the checkpoint's `seq`; it does **not** interpret the
checkpoint body. Deciding whether a checkpoint is one this engine may resume from is
[`read_resume`](pyflow-driver.md)'s job, and a checkpoint whose `engine` key is not `"pyflow"` is
refused there.
- tests: `workhorse/tests/test_artifacts_previous_death.py::test_resume_stamps_a_dead_pid_and_keeps_it_visible_until_finish`, `workhorse/tests/test_artifacts_previous_death.py::test_finish_clears_the_previous_process_stamp_even_when_terminal_is_fail`, `workhorse/tests/test_artifacts_previous_death.py::test_a_resume_against_a_live_pid_does_not_stamp`

### `at`
`at(run_dir, workflow_name, run_id) -> ArtifactWriter` (classmethod)
A fresh writer rooted directly at `run_dir` (no `runs_dir/<name>-<id>` derivation). Mirrors
`__init__`'s fresh-start hygiene — creates `run_dir`, runs `_clear_stale_run` on it (the
full-directory wipe, not a partial unlink, because a flow node inside a loop re-enters this
scope within a single run and the prior story's per-node subdirectories would otherwise be
misread as this story's), sets `_started_at`/`_workflow_name`/`_run_id`/`_seq = 0` plus the
visit-archive bookkeeping (`_turns_root = run_dir` here, rebindable by the caller — see
[`subscope`](#subscope)) and the same nulled prior-process fields as `__init__`, and calls
`_write_run_json(terminal=None)`. Used for a handoff's nested scope (see
[`subscope`](#subscope)), where the run dir is a
node's own subdirectory rather than a sibling of other runs under `runs_dir`.

### `subscope`
`subscope(node_id, flow_name, *, resume=False) -> ArtifactWriter`
Returns the writer for a child workflow handed off at `node_id`, rooted under this run's node
directory (`<run_dir>/<node_id>/_flow`).
- consistency: child-writer — when `resume` is true and `<run_dir>/<node_id>/_flow/checkpoint.json` exists,
  return the child writer resumed from `<run_dir>/<node_id>/_flow`
- consistency: child-writer — otherwise return a fresh child writer rooted at `<run_dir>/<node_id>/_flow`, with
  `flow_name` as its workflow name and `node_id` as its run ID
- consistency: child-turns-archive — the child writer's `turns/` archive is filed at this run's top
  (`child._turns_root = self._turns_root`), not under `<run_dir>/<node_id>/_flow/turns/` —
  the child's scope is emptied on every entry (see [`at`](#at)), and the previous story's
  per-visit copies would be deleted alongside.
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

### `write_state_checkpoint`
`write_state_checkpoint(state, params, *, inputs, flow=None, ctx=None, waiting_on=None) -> int`
The resume point of a Python state machine: the state to (re-)enter and the arguments bound for
it. Written by [`drive`](pyflow-driver.md) **before** dispatching into every state, and a second
time when a state returns `Await` — with `waiting_on` set — so "blocked on a human at `<path>`" is
on disk whether or not the waiting process survives. Returns the new `_seq` (the seq the
checkpoint was written under), so callers can record the under-which value alongside the
node visit they are about to make.
1. `_seq += 1`.
2. Build `data = {engine: "pyflow", workflow, run_id, flow, state, params, waiting_on, inputs,
   ctx, seq, updated_at}`.
3. Hand off to `_write_checkpoint` — write `checkpoint.json.tmp`, then `tmp.replace(path)`,
   atomic rename on the same filesystem, so a crash mid-write still leaves the previous
   checkpoint valid and complete.
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

### `_write_checkpoint`
`_write_checkpoint(checkpoint: Checkpoint) -> None` — private. The atomic-write half of
`write_state_checkpoint`: write `checkpoint.json.tmp`, then `tmp.replace(path)`. The
write-then-rename pattern keeps the resume path from ever meeting a truncated file — a kill
mid-write leaves the previous checkpoint intact rather than half of this one. Reached from
`write_state_checkpoint`; the retired YAML engine wrote through its own path and never
called this.
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter._write_checkpoint`

### `record_node`
`record_node(node_id, phase, **fields)`
The public entry to the append-only event log — `_append_event` with a name callers may use.
A YAML node visit was always bracketed by a checkpoint write and a `done` marker, so the engine
needed no other way in. A Python state machine checkpoints per **state** and runs several nodes
inside one, so its per-node `enter` events need an entry point that is not a checkpoint write.
Called by the engine for each `self.call` (with `blueprint=`), each `self.agent` (with `prompt=`),
and each `self.handoff` (with `flow=`); a dry run adds a stand-in marker.
- code: `workhorse/tests/test_pyflow_graph.py::test_a_dry_run_records_which_stand_in_answered_each_seam`
- tests: `workhorse/tests/test_pyflow_graph.py::test_a_dry_run_records_which_stand_in_answered_each_seam`

### `record_profile`
`record_profile(profile, tables=None)` stores the selected profile name and its starting tables in
`run.json`. The name is used on a flagless resume; the copied tables are informational and are not
read back for turn resolution.
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter.record_profile`

### `record_launch`
`record_launch(argv, resume_argv, cwd)` writes a `LaunchRecord` to `launch.json`: the actual
argv for forensics and a separately rebuilt resume argv, the working directory, the resume
program (derived from `resume_argv[0]`), this process's pid, the wall-clock start, the run
dir's resume generation (read from `workhorse.turnkey`), and a boolean `container` flag
(probed by `/.dockerenv` presence) — a container-marked record is not safe for a host-side
respawn, and the flag is the one fact a host-side reader cannot recover from the record
itself. Best-effort: a write failure is swallowed, because a directory that cannot be
written is a run that is worse off unwatched, not a run that should stop.
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter.record_launch`

### `write_step`
`write_step(node_id, prompt, output, context_after, next_node=None)`
Writes the artifact group for one node visit.
1. `mkdir(run_dir / node_id, exist_ok=True)`.
2. Write `prompt.md` (plain text), `output.json` (`json.dumps(output, indent=2)`),
   `context_after.json` (`json.dumps(context_after, indent=2)`) — each through
   `_write_unlinked`, which `unlink(missing_ok=True)`s the target first so the previous
   visit's hardlinked copy in `turns/` is not truncated through a shared inode.
3. `_keep_visit_copy(node_id, [...same three paths...])` — files the same artifacts into
   `turns/<visit-key>/` for the current `turnkey` key (no-op when no visit is open or the
   visit belongs to another node), hardlinked where the filesystem allows.
4. `_write_done(node_id, next_node)`.

pyflow calls it for a `self.call` (prompt = a rendered `name(args)` description), a `self.agent`
(prompt = the rendered Jinja prompt, or `(dry-run) <path>` under `--dry-run`) and a `self.handoff`
(prompt = `handoff → <ChildClass>`). It always passes `context_after={}` and `next_node=None` —
there is no ambient context to snapshot and no node-graph edge to name — so those two files are
constant in a pyflow run and only `prompt.md`/`output.json` carry information.

### `record_interrupt`
`record_interrupt(node_id, error)`
Records that the run **stopped without deciding** while `node_id` was in flight — an operator
interrupt (Ctrl-C), or `WORKHORSE_MAX_RUNTIME_S` running out between states.
1. `_append_event(node_id=node_id, phase="error", error=error)` — closes that node's `enter`
   window, which otherwise dangles exactly as a wedged node's does.
2. `_write_run_json(terminal=None, error=error)` — stamps `interrupted_at`/`error`.

Without it an interrupted run is indistinguishable on disk from a wedged one, and finding out
which required going to the backend CLI's own session transcript.

Deliberately **not** `finish()`: a non-null `terminal` reads as "this run is over" to
`auto_resolve`/`find_latest_resumable`, and a run that merely stopped is precisely the one that
must still auto-resume in place (see [crash and resume](../flows/workhorse-crash-resume.md)). The
stamp clears itself on the next `_write_run_json` — a `resume`, or the run finishing.

Called by `run_pyflow`'s `KeyboardInterrupt` handler and by its `RunBudgetExceeded` branch, both of
which read the in-flight state name back out of the checkpoint. The budget case is why this is not
just a Ctrl-C concern: a budget stop that stamped `fail` like every other `PyflowError` would be
skipped by `--resume-latest`, making the driver's own advice ("Raise the budget and resume")
impossible to follow through the flag that exists to follow it.

### `finish`
`finish(terminal)`
Ends the run.
1. Write `context.json` = `"{}"` — a placeholder immediately overwritten by the caller's
   [`write_final_context`](#write_final_context); `drive` always calls
   `write_final_context` first, so this only guards a caller that doesn't.
2. Clear the previous-process stamps: `_previous_process_died_at = None`,
   `_previous_process_pid = None`. A finished run has its own end-state to record; the fact
   that some *prior attempt* died ungracefully is not a fact about *this* finished run, and
   keeping it would misread as "this run was wedged mid-flight before terminating".
3. `_write_run_json(terminal=terminal)`.
4. `_append_event(node_id="<run>", phase="terminal", terminal=terminal)`.

`drive` passes `"terminal"` when the entry flow returns `Done`; `run_pyflow` passes `"fail"` when a
`PyflowError` ends the run.

### `write_final_context`
`write_final_context(context)`
Writes `context.json` = `json.dumps(context, indent=2)`, called right before `finish()`. Under
pyflow this is the run's **result**, not a context bag: `drive` writes `{"result": …}` carrying
whatever the entry flow's `Done` returned.

### `read_done`
`read_done(node_id) -> dict | None` reads a node's completion marker and returns `None` when it is
absent or malformed. It remains for the retired YAML engine; pyflow does not fast-forward from it.
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter.read_done`

### `read_context_after`
`read_context_after(node_id) -> dict | None` reads the legacy context snapshot and returns `None`
when absent or malformed. Pyflow writes `{}` and restores `ctx` through its checkpoint instead.
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter.read_context_after`

### `_append_event`
`_append_event(node_id, phase, **fields)` — private
Appends one line to `EVENTS_FILE`: `{ts: <now>, seq: _seq, node: node_id, phase, **fields}` as
JSON followed by `\n`. Best-effort — any `OSError` is swallowed, since instrumentation must never
crash a run. The same record is mirrored to the OTel exporter (`otel.record_event`), which is why
node spans need no other hook: root run and nested handoff scopes alike funnel through here.
Reached via `write_state_checkpoint` (`phase="enter"`), `record_node` (any phase), `_write_done`
(`phase="done"`, adding `next`), `finish` (`phase="terminal"`, adding `terminal`), and
`record_interrupt` (`phase="error"`, adding `error`).

### `_write_done`
`_write_done(node_id, next_node)` — private
Marks `node_id` complete. `mkdir(run_dir / node_id, exist_ok=True)`; write `<node_id>/done.json` =
`{seq: _seq, next: next_node}`; then `_append_event(node_id=node_id, phase="done",
next=next_node)`. Called by `write_step` (and by the retired `write_branch`). The recorded `seq`
was how the YAML engine's fast-forward told "finished under the current checkpoint" from "stale
artifact from an earlier loop visit"; pyflow has no fast-forward — it re-enters the checkpointed
state from the top — so today the field is history rather than a resume input.

### `_write_run_json`
`_write_run_json(terminal, error=None)` — private
Writes `run.json` = `{workflow: _workflow_name, run_id: _run_id, started_at: _started_at, ended_at:
<now if terminal else null>, terminal, interrupted_at: <now if error and not terminal else null>,
error, pid: os.getpid(), repo_start, repo_end: <only at a terminal — observed at the same moment
this call has terminal truth, then cleared by a resume like `ended_at`>, profile, profile_config,
previous_process_died_at: <only set by [`resume`](#resume) when the prior pid is no longer
alive; cleared by [`finish`](#finish) and never default-populated>, previous_process_pid}`. Called
by every constructor (`terminal=None`), by `finish` (`terminal="terminal"`/`"fail"`), and by
`record_interrupt` (`terminal=None`, `error=<why the run stopped>`). Every call rewrites the
whole file, so `interrupted_at`/`error` survive only until the run resumes or ends. The `pid` is
also a telemetry resource attribute; it is recorded here so it survives with telemetry off.

## Visit archive

The plumbing behind the per-visit copies in `turns/<visit-key>/`. Three small helpers, called
from `write_step` (and the retired `write_branch`) — never from user code. Best-effort
throughout: keeping a record of a node must not be the thing that fails the node.

### `_write_unlinked`
`_write_unlinked(path, text) -> None` — `@staticmethod`, private. Replace `path`'s contents
without writing through any link to it. The visit archive hardlinks its files, so a plain
`write_text` would truncate the previous visit's kept copy through the shared inode — every
archived prompt would end up holding the latest visit's text, which is the exact loss the
archive exists to prevent.
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter._write_unlinked`

### `visit_dir`
`visit_dir(node_id) -> Path | None`. Where this visit of `node_id` keeps its own copy, or
`None` when there is no visit to name. Reads `turnkey.current()` — when no visit is open, or
the open visit belongs to another node, returns `None` so `write_step` cannot file a `call`
node's output under a still-current `agent` visit. Otherwise returns
`<_turns_root>/turns/<visit-key-slug>/` (see [`subscope`](#subscope) for the parent-vs-child
distinction).
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter.visit_dir`

### `_keep_visit_copy`
`_keep_visit_copy(node_id, written: list[Path])` — private. Copy this visit's artifacts into
`<_turns_root>/turns/<visit-key>/`. Hardlinks where the filesystem allows, so the second
copy of a megabyte of rendered prompt usually costs an inode; falls back to `shutil.copyfile`
on `OSError`. Each destination is `unlink(missing_ok=True)`d first, so a file rewritten by
a later visit does not truncate the earlier visit's copy through a shared inode. The
per-node directory the artifacts came from keeps its meaning of *latest visit* and its
readers — this is additive.
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter._keep_visit_copy`
- tests: `workhorse/tests/test_turn_records.py::test_a_nested_flows_visits_survive_the_next_entry_to_that_scope`, `workhorse/tests/test_turn_records.py::test_keeping_the_copy_never_fails_the_node`

## Reads

### `read_checkpoint`
`read_checkpoint() -> Checkpoint | None`
Returns `CHECKPOINT_FILE` parsed into the model that owns it (`PyflowCheckpoint` or, for a run
directory written by the retired YAML front-end, `NodeGraphCheckpoint` — both in
[`workhorse/records.py`](#the-records)), or `None` if the file doesn't exist. Unlike the readers
below, a malformed or unrecognizable `checkpoint.json` is **not** caught — the `ValidationError`
raises straight through, because a caller about to resume must not proceed on a checkpoint it
could not read. `run_pyflow` reads it to name the in-flight state when a Ctrl-C arrives, and
catches there because it is already on a failure path.

### `read_output`
`read_output(node_id) -> dict | None`
Returns `<node_id>/output.json` parsed, `None` when the file is absent or unparseable, and
`{"value": data}` when the recorded payload was not a JSON object. Backs
[`self.output(node)`](../workflow-format.md#workflow-subclass) — a state reading back what an
earlier node in the same run
recorded, rather than threading the value through every transition in between. Distinguishing
"absent" from "empty" is deliberate and is the caller's to act on: `self.output` raises
`NodeNotRunError` on `None`, where the YAML template helper this replaced returned `""` for both.

### `read_events`
`read_events() -> list[NodeEvent]`
Reads `EVENTS_FILE` in order; `[]` if the file doesn't exist. Splits on lines, skips blank lines,
parses each non-blank line into a `NodeEvent` and skips (rather than raising on) any line that
fails to validate — an append-only log a kill can truncate mid-line must not make *reading*
instrumentation the thing that fails. The per-node-kind extras ride along on `model_extra`.
Consumers (e.g. a cost/spend scorecard) join the returned records against timestamped provider
spend and git commit history.

## The records

`checkpoint.json` and `events.jsonl` are the two files that survive the process, so they are the
two that are parsed rather than trusted: one pydantic model owns each in both directions, in
[`workhorse/records.py`](../../../../workhorse/workhorse/records.py). `ArtifactWriter` owns the
files; that module owns their shape and does no I/O of its own.

- **`PyflowCheckpoint`** — what `write_state_checkpoint` writes and a resume reads. `params` /
  `inputs` / `ctx` are opaque workflow data whose vocabulary is not interpreted by workhorse.
  `workflow`, `run_id` and `updated_at` are annotations nothing reads back, so their defaults let an
  operator hand-trim them from a long-running checkpoint without preventing resume.
- consistency: pyflow-checkpoint — `PyflowCheckpoint.engine` accepts only `"pyflow"`, so parsing refuses a checkpoint
  that identifies another engine.
- consistency: pyflow-checkpoint — `PyflowCheckpoint.state` is required and non-empty, so parsing refuses a checkpoint
  that cannot name the state to resume.
- **`NodeGraphCheckpoint`** — the retired YAML engine's shape (`current_id` + `context`), kept as a
  union member so `read_resume` can still recognize such a run directory and refuse it *by name*
  rather than by coincidence.
- **`NodeEvent`** — one `events.jsonl` line: `ts`, `seq`, `node`, and a `phase` closed to
  `enter`/`done`/`terminal`/`error`. Everything else a caller passes (`next`, `waiting_on`,
  `blueprint`, `model`, …) is `extra="allow"` and stays a **top-level** key on disk, because
  scorecards outside this repo join these lines — nesting them under an `extra` object would be a
  format change wearing a refactor's clothes.

## Retired with the YAML engine

Still on the class, still covered by tests, **no production caller**. Listed so the methods are
identifiable when they turn up in a test or in a run directory written by the old front-end.

### `write_checkpoint`
`write_checkpoint(current_id, context)`
The YAML engine's checkpoint: the *node* about to run plus the whole ambient context bag, at
`{workflow, run_id, current_id, seq, context, updated_at}` — a `current_id` and no `engine` key,
which is what lets `NodeGraphCheckpoint` claim it off disk and `read_resume` refuse it by name.
Superseded by
[`write_state_checkpoint`](#write_state_checkpoint).

### `write_branch`
`write_branch(node_id, path, value, next_node)`
Wrote `<node_id>/branch.json` = `{path, value, next: next_node}` for a `branch` node — routing
only, no prompt/output/context-diff — then `_write_done`. There is no `branch` node type in a
Python workflow: a branch is an ordinary `if` inside a state method, and the edge it picks is the
`Continue` that state returns.

### `read_done`
`read_done(node_id) -> dict | None`
Returned `<node_id>/done.json` parsed, or `None` if absent or unparseable. Fed the YAML engine's
fast-forward decision, which pyflow does not have.

### `read_context_after`
`read_context_after(node_id) -> dict | None`
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
