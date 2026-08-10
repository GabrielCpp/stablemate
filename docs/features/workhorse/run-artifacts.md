---
type: format
slug: run-artifacts
title: Run artifacts
---
# Run artifacts

The on-disk record of one [`workhorse-<name> run`](workhorse.md#run) execution: a directory tree written
incrementally by an `ArtifactWriter` as [`drive`](concepts/pyflow-driver.md) walks the workflow's
state machine. It serves two purposes at once — **checkpointing** (so a killed run resumes in the
state it stopped in) and **history** (every prompt, output and event survives the run, read back by
a workflow's own tests and by a cost/spend scorecard). A child workflow entered via `self.handoff`
gets its own nested instance of this same layout, rooted under the calling node's directory.

- file: `<runs-dir>/<workflow-name>-<run-id>/` (a directory tree, not a single file; `<runs-dir>`
  defaults to `<cwd>/.agents/runs`; `<run-id>` is the explicit `--run-id`, else a digest of
  `--params` (`p<sha1[:8]>`), else `default` — see [`run`](workhorse.md#run))
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter`
- verify: `workhorse/tests/test_pyflow.py::test_the_checkpoint_is_the_state_and_its_params`,
  `workhorse/tests/test_pyflow.py::test_a_resume_re_enters_the_checkpointed_state_without_re_running_setup`,
  `workhorse/tests/test_pyflow.py::test_await_writes_the_ask_and_checkpoints_before_it_waits`,
  `workhorse/tests/test_idempotency.py::test_checkpoint_seq_increments`

## Layout

```
<runs-dir>/
└── <workflow-name>-<run-id>/
    ├── run.json               # run-level metadata (start/end time, terminal state, pid, repo state)
    ├── checkpoint.json        # the state to (re-)enter and its params (overwritten every step)
    ├── events.jsonl           # append-only event log (enter/done/terminal/error)
    ├── context.json           # the run's result (written once, at finish)
    ├── .session_id            # current backend session id (plain text; agent turns only)
    ├── sessions.jsonl         # append-only node → backend session id map, one line per turn
    ├── resume_generation      # how many times this run dir has been started (telemetry writes it)
    ├── turn_seq               # the run's monotone agent-node visit counter
    └── <node-id>/             # one subdirectory per node visited
        ├── prompt.md          # what was sent/run for this node
        ├── output.json        # the node's recorded return value
        ├── context_after.json # always {} under pyflow (see below)
        ├── done.json          # completion marker: {seq, next}
        └── _flow/             # handoff only: a nested instance of this whole layout,
                               # rooted here instead of under <runs-dir>
```

A `<node-id>` is the node function's registered name for a `self.call`, the prompt template's
**stem** for a `self.agent`, and the child workflow's class name for a `self.handoff`. A node
visited more than once (a loop, or a state re-entered after a resume) overwrites its directory's
contents on each visit — only the latest visit's artifacts survive, except `events.jsonl` and
`sessions.jsonl`, which accumulate one line per visit.

Because pyflow re-enters a checkpointed state **from the top**, a resumed run re-runs whatever that
state had already done inside itself, rewriting those node directories. That is the coarse-resume
bargain: what a state owes is idempotency, not determinism — see
[crash and resume](flows/workhorse-crash-resume.md).

## Fields

### run.json
- type: `object` — required: yes — default: n/a (always written, both on fresh start and resume)

Run-level metadata, rewritten by `ArtifactWriter._write_run_json` each time the run's terminal
state changes:
- `workflow` — type `string`, required — the workflow's entry-point name.
- `run_id` — type `string`, required — the resolved run id (see the `file:` bullet above).
- `started_at` — type `string` (ISO-8601 UTC), required — set once, at writer construction (a
  resume preserves the original `started_at` by reading it back from the existing `run.json`).
  This is what anchors `WORKHORSE_MAX_RUNTIME_S` to the run's original start rather than to the
  latest relaunch.
- `ended_at` — type `string | null` (ISO-8601 UTC) — default `null`; set only when the run reaches a
  terminal state (`finish()` is called); `null` while the run is in progress, including immediately
  after a resume (re-marked in-progress until it finishes again).
- `terminal` — type `enum{terminal,fail} | null` — default `null` (in progress); `terminal` when the
  entry flow returned [`Done`](workflow-format.md#transition), `fail` when a `PyflowError` ended the
  run. One `PyflowError` is deliberately excluded: `RunBudgetExceeded` records itself as a stop
  (below) instead, because a run cut off by the clock decided nothing and must stay resumable.
- `interrupted_at` — type `string | null` (ISO-8601 UTC) — default `null`; set by
  [`record_interrupt`](concepts/artifact-writer.md#record_interrupt) when the run **stopped
  without deciding** — an operator Ctrl-C, or `WORKHORSE_MAX_RUNTIME_S` running out between
  states. `terminal` stays `null` (such a run must remain auto-resumable), so this field is what
  separates *stopped* from *still in flight, or wedged in a node* — which are otherwise the same
  bytes on disk. Cleared by the next write: a resume, or the run finishing.
- `error` — type `string | null` — default `null`; why the run stopped, accompanying
  `interrupted_at` — `KeyboardInterrupt`, or the `RunBudgetExceeded` message naming the budget.
- `pid` — type `int`, required — the writing process's pid. Also a telemetry resource attribute;
  recorded here so it survives with telemetry off.
- `repo_start` — type `object | null` — default `null`; what `git` said about the run's working
  tree when the run directory was created, as `{path, head, branch, dirty}`. Written by
  [`workhorse.gitstate`](#repo-state), which **observes** rather than predicts — a workflow node,
  or the agent inside a turn, may commit, branch, rebase or check out at any moment, and the
  directory may not be a working tree at all. Carried across a resume rather than re-observed, so
  it keeps meaning *what the run started from* instead of *what the last process happened to see*.
  `null` where there was nothing to observe; every field is optional on read, so a `run.json`
  written before this existed still parses.
- `repo_end` — type `object | null` — default `null`; the same observation at the moment the run
  reached a terminal. Cleared by a resume, exactly as `ended_at` is. Only written at a terminal:
  every other write of this file happens while the run is still going, where an "end" would be
  overwritten by the next one anyway.

#### Repo state

The same observation reaches telemetry, because a recorded turn that cannot be matched to the
code the agent was reading is *what happened, somewhere*:

- **spans** — the root span, every node/state span and every agent-turn span carry
  `git.head.start` at open and `git.head.end` at close. Unequal endpoints mean something moved
  HEAD inside that span. That is a **record, not an error** — nothing in the engine asserts the
  two should be equal, and nothing models why they differ.
- **logs** — each record shipped to the collector carries a `head` attribute: the commit current
  when it was emitted. It cannot be a resource attribute (the resource is frozen when the provider
  is built, and this run's HEAD moves), so a `logging` filter stamps it at emit.

Reads are cheap by construction: HEAD is cached with a short TTL and re-read only at boundaries,
because a `git rev-parse` per log line is not affordable. The cost is that a record emitted
seconds after a mid-turn checkout may carry the previous hash; the span endpoints bracket the move
regardless. Every git call is best-effort behind a timeout — a run must never die because it could
not describe itself — so a missing `git`, a non-repository directory or a hung filesystem yields an
**absent** field rather than a blank or a zero. Absent means *not observed*, which is why `dirty`
is tri-state: `null` is "did not look, or could not tell", never "clean".

### checkpoint.json
- type: `object` — required: yes — default: absent until the first state is about to run

The resume point: **which state is about to be entered, and the arguments bound for it**.
Overwritten atomically (write to `checkpoint.json.tmp`, then rename) by
[`write_state_checkpoint`](concepts/artifact-writer.md#write_state_checkpoint)
immediately before that state runs — so a crash mid-state still leaves a valid, complete prior
checkpoint. Dropped (unlinked) at the start of any *fresh* run (not a resume) so a reused stable
dir never resurrects a finished run's state.
- `engine` — type `string`, required — always `"pyflow"`. A fail-closed discriminator: the retired
  YAML front-end shared this runs directory and wrote a checkpoint with no `engine` key, and one of
  its node ids that happened to match a state name would otherwise resume the wrong thing. A
  checkpoint that does not carry `"pyflow"` is
  [refused by name](concepts/pyflow-driver.md#a-checkpoint-from-the-retired-engine-is-refused-not-misread).
- `workflow` — type `string`, required.
- `run_id` — type `string`, required.
- `flow` — type `string | null`, required — the `Workflow` **class** name, so a bare
  `--resume-latest` re-enters the flow that wrote the checkpoint rather than the distribution's
  default one.
- `state` — type `string`, required — the state method about to be entered.
- `params` — type `object`, required — that state's own named arguments, flat and small enough to
  read (and hand-edit) at hour 30 of a stuck run.
- `waiting_on` — type `string | null`, required — the path an [`Await`](workflow-format.md#transition)
  is blocked on, written **before** the wait begins; `null` otherwise.
- `inputs` — type `object`, required — the run's frozen constructor inputs.
- `ctx` — type `any`, required — the `self.ctx` written once by `setup()`, carried here so a resume
  reconstructs the instance **without** re-running `setup()`.
- `seq` — type `int`, required — monotonic checkpoint counter, incremented on every write. A node's
  `done.json` records the `seq` it ran under. pyflow does not read it back — it has no fast-forward
  — so it is history rather than a resume input.
- `updated_at` — type `string` (ISO-8601 UTC), required.

### events.jsonl
- type: `list<object>` (JSON Lines — one JSON object per line) — required: no — default: absent
  (read back as `[]`)

Append-only history log; unlike `checkpoint.json` (overwritten every step) this preserves every
state and node visit, so a cost/spend scorecard can attribute provider spend and git commits to
individual nodes by joining them against these timestamped windows. Read back via `read_events`.
Dropped (unlinked) at the start of a fresh run, same as `checkpoint.json`. Writes are best-effort —
an `OSError` is swallowed so instrumentation can never crash a run. Each record is also mirrored to
the OTel exporter, which is why node spans need no other hook. Each line:
- `ts` — type `string` (ISO-8601 UTC), required.
- `seq` — type `int`, required — the checkpoint seq active when the event was recorded.
- `node` — type `string`, required — the **state** name for a checkpoint's `enter`, the node id for
  a node's `enter`/`done`, or the literal `<run>` for the run-level `terminal` event.
- `phase` — type `enum{enter,done,terminal,error}`, required.
- extra fields — merged in by the call site: a state `enter` adds `waiting_on` (type
  `string | null`); a node `enter` adds `blueprint` (a `self.call`), `prompt` (a `self.agent`) or
  `flow` (a `self.handoff`), plus a stand-in marker under `--dry-run`; a `done` event adds `next`
  (type `string | null`, always `null` under pyflow); the run-level `terminal` event adds `terminal`
  (type `enum{terminal,fail}`); an `error` event adds `error` (type `string`) and closes the
  in-flight node's `enter` window when a Ctrl-C stops the run (see
  [`record_interrupt`](concepts/artifact-writer.md#record_interrupt)).

### context.json
- type: `object` — required: no — default: `{}` (present only after the run reaches a terminal
  state)

The run's **result**, written once by `write_final_context` right before the run finishes:
`{"result": …}` carrying whatever the entry flow's [`Done`](workflow-format.md#transition) returned.
`finish()` itself first stamps a placeholder `"{}"` (overwritten by the caller's
`write_final_context` immediately after) — a defensive ordering `drive` already satisfies by calling
`write_final_context` first.

The name is a holdover from the retired engine, where this file held the final ambient context bag.
A Python workflow has no such bag: state lives in the state's parameters and in `self.ctx`.

### .session_id
- type: `string` (plain text, not JSON) — required: no — default: absent

The active agent backend's session id for **the current node**, written/overwritten by
[`AgentRunner.run`](concepts/run-agent.md) after each successful turn. Deleted before a node's first
attempt unless that node is a genuine resume-after-kill (`resume_session=True`), so every node
other than a resumed one starts its agent CLI with a clean session — see
[`AgentRunner.run`'s session model](concepts/run-agent.md#sessions) and
[workhorse's session model](../../../workhorse/docs/DEVELOPMENT.md#sessions-per-turn-clean-context). Not
managed by `ArtifactWriter`; lives at the run dir root, one file shared (and overwritten) across all
agent turns in the run.

### sessions.jsonl
- type: `list<object>` (JSON Lines) — required: no — default: absent

The durable node → backend-session map, appended by [`AgentRunner.run`](concepts/run-agent.md) after each
successful turn. `.session_id` only ever holds the *current* node's session, so this manifest is
what maps a **past** node back to the session transcript carrying its reasoning and tool trace —
the detail `prompt.md`/`output.json` do not keep. The same mapping is advertised on the agent-turn
span; this file is the copy that needs no collector. A node can appear more than once (a loop
revisit, or a retry inside one node), which is what the visit key below addresses. Best-effort: a
write failure is swallowed. Each line:
- `node` — type `string`, required.
- `session_id` — type `string`, required.
- `generation` — type `int`, optional — how many times this run directory had been started
  (`resume_generation`), read, never incremented, by `workhorse.turnkey`.
- `seq` — type `int`, optional — the run's monotone agent-node **visit** counter (`turn_seq`). With
  `generation` it names the visit, and it is the same key naming that visit's stored prompt. Both
  are omitted for a turn taken outside a visit the engine opened — a library caller driving the
  runner directly — because a wrong number is worse than none.
- `ts` — type `int`, optional — epoch seconds, so a line can be placed against the run's spans and
  logs without inferring order from file position. `(generation, ts)` is a total order that survives
  a checkpoint rewind: a rewind cannot decrease the generation, and this log is append-only, so
  re-running a node adds rows rather than rewriting one.
- `backend` — type `string`, optional — which CLI's vocabulary the session id is in. `opencode
  export <id>` and `~/.claude/projects/` are not interchangeable and the id does not say which.
- `head` — type `string`, optional — the commit the run's tree was on when the turn was recorded
  (see [Repo state](#repo-state)), observed rather than assumed.

Every key beyond the first two is optional on read: lines written before they existed still parse,
and a consumer treats an absent key as *not recorded*, never as a default.

### `<node-id>/prompt.md`
- type: `string` (plain text) — required: no — default: absent

What drove that node's step, written by `write_step`: the rendered Jinja2 prompt for a
[`self.agent`](workflow-format.md#the-agent-turn) turn (prefixed `(dry-run) ` with the template path
under `--dry-run`), a rendered `name(args)` description for a
[`self.call`](workflow-format.md#node), or `handoff → <ChildClass>` for a `self.handoff`.

### `<node-id>/output.json`
- type: `object` — required: no — default: absent until the node runs

The node's recorded return value — a `BaseModel` dumped to JSON, or any JSON-able value. Read back
by [`self.output(node)`](workflow-format.md#workflow-subclass) via `read_output`, which is how a
later state reads what an earlier node produced without threading it through every transition in
between. A non-object payload is wrapped as `{"value": …}`.

### `<node-id>/context_after.json`
- type: `object` — required: no — default: absent until the node runs

Always `{}` under pyflow. The retired engine wrote the full ambient context here after merging a
node's outputs; a Python workflow has no ambient context to snapshot, and the engine passes `{}` at
every call site. The file is still written so the node directory's shape is unchanged.

### `<node-id>/done.json`
- type: `object` — required: no — default: absent until the node completes

Completion marker for the node, written by `_write_done` after its step files.
- `seq` — type `int`, required — the checkpoint `seq` this node ran under (see
  [`checkpoint.json`](#checkpointjson)).
- `next` — type `string | null`, required — always `null` under pyflow. There is no node graph and
  therefore no edge to name: what runs next is whatever
  [`Continue`](workflow-format.md#transition) the enclosing state returns, and that is recorded in
  the checkpoint, not here.

### `<node-id>/_flow/`
- type: directory (a nested instance of this same [Layout](#layout)) — required: no — default:
  absent (`self.handoff` only)

The child run tree for one handoff, rooted at `<node-id>/_flow/` instead of a fresh
`<runs-dir>/<name>-<id>/` — via [`subscope`](concepts/artifact-writer.md#subscope).
A handoff nested inside a handed-off workflow nests one `_flow/` deeper. The engine always enters
this scope **fresh**: pyflow checkpoints the *parent* state, so a resume re-enters that state and
re-runs the handoff from the top rather than resuming into the child's own checkpoint.

## `ArtifactWriter` — the writer

The class that owns this layout end to end: constructing/locating the run dir, the fresh-start vs
resume hygiene (dropping a stale `checkpoint.json`/`events.jsonl`), and every write above. Its
constructors (`__init__`, `resume`, `at`, `subscope`) and methods (`write_state_checkpoint`,
`record_node`, `write_step`, `record_interrupt`, `finish`, `write_final_context`, `read_checkpoint`,
`read_output`, `read_events`) are documented in full as their own concept:
[`ArtifactWriter`](concepts/artifact-writer.md), which also lists the four methods that survived the
YAML engine's retirement without a production caller.

- code: `workhorse/workhorse/artifacts.py::ArtifactWriter`

## Consumers

- [`drive`](concepts/pyflow-driver.md) — writes `checkpoint.json` before every transition and again
  before an `Await` waits, then `context.json` and `run.json`'s terminal stamp when the entry flow
  returns `Done`.
- `run_pyflow` — seeds or resumes the run dir, reads `checkpoint.json` back to name the in-flight
  state on a Ctrl-C, and marks `run.json` `fail` when a `PyflowError` ends the run.
- A workflow's own tests — a test hands `drive` a `RunEnv` whose writer points at pytest's
  `tmp_path`, then asserts on `checkpoint.json`, `run.json` and the per-node `output.json`; see
  [authoring a test suite](flows/workhorse-author-test.md).
- A cost/spend scorecard (external to workhorse) — joins `events.jsonl`'s timestamped node windows
  against provider spend and git commit history, and `sessions.jsonl` to reach each turn's
  transcript.
