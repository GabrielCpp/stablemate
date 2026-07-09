---
type: format
slug: run-artifacts
title: Run artifacts
---
# Run artifacts

The on-disk record of one [`workhorse run`](workhorse.md#run) execution: a directory tree written
incrementally, node by node, by an `ArtifactWriter` as the [workflow](concepts/workflow.md) graph is
walked. It serves two purposes at once — **checkpointing** (so a killed run resumes exactly where
it stopped) and **history** (every prompt/output/context snapshot survives the run, read back by
[`workhorse.testing`](concepts/testing.md)'s `RunResult` and by a cost/spend scorecard). A flow
invoked via a `flow` node gets its own nested instance of this same layout, rooted under the
calling node's directory.

- file: `<runs-dir>/<workflow-name>-<run-id>/` (a directory tree, not a single file; `<runs-dir>`
  defaults to `<workflow-dir>/runs`, `<run-id>` to `default` — see [`run`](workhorse.md#run)'s
  `--runs-dir`/`--run-id` flags)
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter`
- verify: `workhorse/tests/test_call_node.py::test_call_node_end_to_end`,
  `workhorse/tests/test_idempotency.py::test_checkpoint_seq_increments`,
  `workhorse/tests/test_flows.py::test_resume_across_flow_boundary`

## Layout

```
<runs-dir>/
└── <workflow-name>-<run-id>/
    ├── run.json                 # run-level metadata (start/end time, terminal state)
    ├── checkpoint.json           # current position + full context (overwritten every step)
    ├── events.jsonl               # append-only per-node event log (enter/done/terminal)
    ├── context.json              # final context snapshot (written once, at finish)
    ├── .session_id                # current backend session id (plain text; agent nodes only)
    └── <node-id>/                 # one subdirectory per node visited
        ├── prompt.md               # agent/script/call/flow: the text sent/run for this node
        ├── output.json             # the node's extracted/declared outputs
        ├── context_after.json      # full context snapshot after this node merged its outputs
        ├── done.json               # completion marker: {seq, next}
        ├── branch.json             # branch nodes only, in place of the four files above
        └── _flow/                  # flow nodes only: a nested instance of this whole layout,
                                     # rooted here instead of under <runs-dir>
```

A node directory holds either the `prompt.md`/`output.json`/`context_after.json`/`done.json` group
(agent, script, call, and flow nodes — `ArtifactWriter.write_step`) or `branch.json` alone (branch
nodes — `ArtifactWriter.write_branch`); never both. A node visited more than once (a loop body, or a flow re-entered inside a loop)
overwrites its directory's contents on each visit — only the latest visit's artifacts survive,
except `events.jsonl`, which accumulates one line per visit.

## Fields

### run.json
- type: `object` — required: yes — default: n/a (always written, both on fresh start and resume)

Run-level metadata, rewritten by `ArtifactWriter._write_run_json` each time the run's terminal
state changes:
- `workflow` — type `string`, required — the workflow's `name` (from `workflow.yaml`).
- `run_id` — type `string`, required — the `--run-id` value (or `default`).
- `started_at` — type `string` (ISO-8601 UTC), required — set once, at writer construction (a
  resume preserves the original `started_at` by reading it back from the existing `run.json`).
- `ended_at` — type `string | null` (ISO-8601 UTC) — default `null`; set only when the run reaches a
  terminal state (`finish()` is called); `null` while the run is in progress, including immediately
  after a resume (re-marked in-progress until it finishes again).
- `terminal` — type `enum{terminal,fail} | null` — default `null` (in progress); the terminal node's
  `type` once the run ends.

### checkpoint.json
- type: `object` — required: yes — default: absent until the first node is about to run

The resume point: which node is about to execute and the full context it carries. Overwritten
atomically (write to `checkpoint.json.tmp`, then rename) on every `write_checkpoint` call,
immediately before that node runs — so a crash mid-node still leaves a valid, complete prior
checkpoint. Dropped (unlinked) at the start of
any *fresh* run (not a resume) so a reused stable dir never resurrects a finished run's state.
- `workflow` — type `string`, required.
- `run_id` — type `string`, required.
- `current_id` — type `string`, required — the node id about to run.
- `seq` — type `int`, required — monotonic checkpoint counter, incremented on every write; a node's
  `done.json` records the `seq` it ran under so resume can tell "finished under the current
  checkpoint" (fast-forward past it) from "stale artifact from an earlier visit" (re-run it). See
  [workflow execution](concepts/workflow.md#execution) for the fast-forward rule.
- `context` — type `object`, required — the full [`WorkflowContext`](concepts/workflow-context.md)
  dict going into `current_id`.
- `updated_at` — type `string` (ISO-8601 UTC), required.

### events.jsonl
- type: `list<object>` (JSON Lines — one JSON object per line) — required: no — default: absent
  (read back as `[]`)

Append-only, per-node history log; unlike `checkpoint.json` (overwritten every step) this preserves
every node visit, so a cost/spend scorecard can attribute provider spend and git commits to
individual nodes by joining them against these timestamped windows. Read back via `read_events`.
Dropped (unlinked) at the start of a fresh run, same as `checkpoint.json`. Writes are best-effort — an `OSError` is swallowed so instrumentation can never
crash a run. Each line:
- `ts` — type `string` (ISO-8601 UTC), required.
- `seq` — type `int`, required — the checkpoint seq active when the event was recorded.
- `node` — type `string`, required — the node id, or the literal `<run>` for the run-level
  `terminal` event.
- `phase` — type `enum{enter,done,terminal}`, required.
- extra fields — merged in by the call site: a `done` event adds `next` (type `string | null`); the
  run-level `terminal` event adds `terminal` (type `enum{terminal,fail}`); an `enter` event carries
  no extra fields today.

### context.json
- type: `object` — required: no — default: `{}` (present only after the run reaches a terminal
  node)

The final [`WorkflowContext`](concepts/workflow-context.md) snapshot, written once by `write_final_context`
right before the run finishes. `finish()` itself first stamps a placeholder `"{}"` (overwritten by
the caller's `write_final_context` immediately after) — a defensive ordering the top-level `run()`
and `_run_flow` both follow, calling `write_final_context` before `finish`.

### .session_id
- type: `string` (plain text, not JSON) — required: no — default: absent

The active agent backend's session id for **the current node**, written/overwritten by
[`run_agent`](concepts/run-agent.md) after each successful turn. Deleted before a node's first
attempt unless that node is a genuine resume-after-kill (`resume_session=True`), so every node
other than a resumed one starts its agent CLI with a clean session — see
[`run_agent`'s session model](concepts/run-agent.md#sessions) and
[workhorse's session model](../../../workhorse/README.md#sessions-per-node-clean-context). Not
managed by `ArtifactWriter`; lives at the run dir root, one file shared (and overwritten) across all
agent nodes in the run.

### `<node-id>/prompt.md`
- type: `string` (plain text) — required: no — default: absent (only agent/script/call/flow nodes
  write one)

The text driving that node's step, written by `write_step`: the rendered Jinja2 prompt for an
`agent` node, the rendered command string for a `script` node, a human-readable call label for a
`call` node, or the literal string `flow:<flow-name>` for a `flow` node.

### `<node-id>/output.json`
- type: `object` — required: no — default: absent (agent/script/call/flow nodes only)

The node's declared `outputs`, merged into the [`WorkflowContext`](concepts/workflow-context.md) for
every subsequent node.

### `<node-id>/context_after.json`
- type: `object` — required: no — default: absent (agent/script/call/flow nodes only)

The full [`WorkflowContext`](concepts/workflow-context.md) dict immediately after this node's
outputs were merged in — read back on
resume (via `read_context_after`) to restore context when fast-forwarding past an already-completed
node.

### `<node-id>/done.json`
- type: `object` — required: no — default: absent until the node completes

Completion marker for the node, written by `_write_done` after its step files. Written for both the
`write_step` group and (see [`<node-id>/branch.json`](#node-idbranchjson)) branch nodes.
- `seq` — type `int`, required — the checkpoint `seq` this node ran under (see
  [`checkpoint.json`](#checkpointjson)).
- `next` — type `string | null`, required — the node id to advance to (`null` only if the graph is
  malformed — every real edge names a `next`/branch target).

### `<node-id>/branch.json`
- type: `object` — required: no — default: absent (branch nodes only; mutually exclusive with the
  `prompt.md`/`output.json`/`context_after.json` group above)

Written by `write_branch` instead of `write_step` for a `branch` node — a branch has no
prompt/output/context-diff of its own, just the routing decision.
- `path` — type `string`, required — the branch's dot-path into context (from `workflow.yaml`'s
  `path:` key).
- `value` — type `any`, required — the value resolved at that path.
- `next` — type `string`, required — the node id the branch routed to (a `cases`/`conditions` match
  or the `default`).

### `<node-id>/_flow/`
- type: directory (a nested instance of this same [Layout](#layout)) — required: no — default:
  absent (`flow` nodes only)

The child run tree for one `flow` node invocation, rooted at `<node-id>/_flow/` instead of a fresh
`<runs-dir>/<name>-<id>/` — via `subscope`. A `flow` node nested inside another flow nests one
`_flow/` deeper (`.../. _flow/<node-id>/_flow/...`). Whether this directory's
`checkpoint.json`/`events.jsonl` are dropped (fresh entry) or preserved (genuine mid-flow resume) is
decided by the engine's resume signal, not by whether a checkpoint happens to already exist — see
[workflow execution](concepts/workflow.md#execution).

## `ArtifactWriter` — the writer

The class that owns this layout end to end: constructing/locating the run dir, the fresh-start vs
resume hygiene (dropping a stale `checkpoint.json`/`events.jsonl`), and every write above. Its
constructors (`__init__`, `resume`, `at`, `subscope`) and methods (`write_checkpoint`, `write_step`,
`write_branch`, `finish`, `write_final_context`, `read_checkpoint`, `read_done`,
`read_context_after`, `read_events`) are documented in full as their own concept:
[`ArtifactWriter`](concepts/artifact-writer.md).

- code: `workhorse/workhorse/artifacts.py::ArtifactWriter`

## Consumers

- [workflow execution](concepts/workflow.md#execution) — `write_checkpoint`/`read_checkpoint`/
  `read_done`/`read_context_after` drive the checkpoint/fast-forward/resume logic.
- [`workhorse.testing`](concepts/testing.md)'s `RunResult` — reads `context.json`, `checkpoint.json`,
  `<node-id>/output.json`, and `<node-id>/prompt.md` (resolving `_flow`-nested node ids) to make
  assertions about a completed test run.
- A cost/spend scorecard (external to workhorse) — joins `events.jsonl`'s timestamped node windows
  against provider spend and git commit history.
