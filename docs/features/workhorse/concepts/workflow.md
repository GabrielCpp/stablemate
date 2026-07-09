---
type: concept
slug: workflow
title: Workflow — a YAML-defined agent graph workhorse executes
---
# Workflow

A directed graph of nodes that [workhorse](../workhorse.md) executes **fail-soft**,
checkpointing after every node so a run resumes exactly where it stopped (built to run
unattended for days), each `agent` node driven by an [AgentBackend](agent-backend.md) harness.
Its on-disk shape is the [workflow file format](../workflow-format.md),
which [load_workflow](load-workflow.md) parses into the pydantic `Graph` modeled here;
[workhorse run](../workhorse.md#run) then walks it. A run's live state is a
[`WorkflowContext`](workflow-context.md) — a key→value bag with dot-path lookup for branches —
plus resumable run artifacts. The exhaustive field reference is
[the workflow file format](../workflow-format.md) (and `workhorse/docs/WORKFLOW.md`). Each
non-terminal node type is stepped by its own handler — [run_script](run-script.md) (`script`),
[evaluate](evaluate-branch.md) (`branch`), [run_flow](run-flow.md) (`flow`),
[run_call](run-call.md) (`call`, dispatching through the [builtins registry](builtins-registry.md))
— with the walk itself guarded by the [gas tank](gas-tank.md) and recorded by the
[ArtifactWriter](artifact-writer.md).

- code: `workhorse/workhorse/graph/nodes.py::Graph`

## Node types

Every node has an `id`, a `type`, and (except `terminal`/`fail`) a `next`. The set is fixed:

- **`agent`** — run an LLM against a Jinja `prompt` with rendered `args`, extracting the declared
  `outputs`. An optional `power` tier (low/medium/high) maps to a model via
  [workhorse config](../workhorse.md#config); the harness driving it is an
  [AgentBackend](agent-backend.md). The retry → reframe → default resilience ladder lives here.
- **`script`** — run a shell/Python script, capturing one JSON object from stdout as its
  `outputs`. Receives the workflow's `env` (below) in its subprocess environment. Stepped by
  [run_script](run-script.md).
- **`branch`** — route to a `next` by matching a context dot-`path` against `cases` (equality) or
  `conditions` (numeric `==`/`!=`/`<`/`>`/`<=`/`>=`), falling back to `default`. Stepped by
  [evaluate](evaluate-branch.md).
- **`flow`** — call a named sub-graph from [flows](../workflow-format.md#flows) like a function
  (see [Flows](#flows) below). Stepped by [run_flow](run-flow.md).
- **`call`** — invoke a builtin `fn` with rendered `args`, capturing `outputs`; a lightweight
  step with no LLM and no subprocess. Stepped by [run_call](run-call.md), which looks the `fn` up
  in the [builtins registry](builtins-registry.md).
- **`terminal`** / **`fail`** — end the run: exit 0 and exit 1 respectively.

## Flows

A **flow** is a named sub-graph — itself a full `Graph` — held in the workflow's
[flows](../workflow-format.md#flows) map. A `flow` node runs one like a function: the caller
passes `args`, and the flow executes against its **own isolated `vars`**, so parent state can't
silently leak in and the boundary stays explicit. A flow is also runnable standalone as a
re-entry point — [`workhorse run <workflow> <flow>`](../workhorse.md#run), e.g.
`workhorse run coder qa` — which is how a long workflow's phases (dev / review / qa) are launched
in isolation.

## Context — vars and env

- **`vars`** — the workflow's initial [context](../workflow-format.md#vars). A flow `var` with a
  null default is a **required** parameter (missing at launch → error); an empty-string default is
  **optional**. Overridden on a fresh start by [run](../workhorse.md#run)'s `--params` /
  `--params-file` (ignored on resume). Nodes read it in Jinja `args` and branch `path`s.
- **`env`** — workflow-level environment variables (Jinja-rendered from context) injected into
  **every `script` node**'s subprocess. A node's own `env` merges on top, so a node can override
  individual keys.

## Execution

`run` (`workhorse/workhorse/main.py::run`) is the top-level entry both `workhorse run` (via
`_run_run`, see [workhorse run](../workhorse.md#run)) and [`workhorse.testing`](testing.md) call.
It owns a run's whole lifecycle — picking which graph to walk, deciding fresh-start vs. resume,
and turning the walk's outcome into a process exit code. The node-by-node walk itself is a
separate, shared engine (`_step_loop`) that `run` calls once for the top graph and that a `flow`
node (via `_run_flow`) calls again for every nested sub-graph; see [Node types](#node-types) above
for what each node type does when stepped.

1. **Load and pick the graph.** [`load_workflow`](load-workflow.md) parses `workflow_path` into a
   `Graph`. If a `flow` name was passed (the `workhorse run <workflow> <flow>` re-entry point),
   that named [flow](#flows) becomes the graph this call runs top-level — **not** a nested
   `_run_flow` call — so it gets its own run dir, checkpoint, and resume independent of the parent
   workflow:
   - an unknown flow name prints `error: workflow '<name>' has no flow '<flow>'. Available flows:
     <sorted list, or "(none)">` to stderr and returns `1`;
   - a flow `var` with a `null` default is **required**; one missing from both `params` and its own
     default prints `error: flow '<flow>' requires params: <missing keys>` plus the full
     `var=default` contract and a `--params` hint, and returns `1`.
2. **Seed the manifest.** `manifest = context_manifest or {}` — the
   [context manifest](../context-manifest.md) is always the outer layer of context (the workflow's
   own `vars`, `--params`, and every node's outputs override it), so farrier's template helpers
   keep resolving even without repo context.
3. **`--no-cache`.** If set and no explicit `resume_run_dir` was passed, delete the stable run dir
   (`<runs_dir>/<graph.name>-<run_id or "default">`) if it exists, forcing the next step to start
   clean.
4. **Auto-resolve the run dir** (`_auto_resolve`, `main.py`). If no explicit `resume_run_dir` and
   `auto` (always `true` from the CLI): compute the single stable dir for
   `(graph.name, run_id or "default")`; resume it if it holds an unfinished checkpoint (a
   `run.json` with `terminal` still `null`); a dir with no checkpoint, or one whose `run.json`
   shows a finished run, is left as a **fresh** start in that same dir — re-running a finished
   program starts a new run rather than replaying it.
5. **Resume vs. fresh.** `resume_interrupted_node` starts `False` — it becomes `True` only when
   this run is re-entering the exact node that was killed mid-turn, so *only* that node resumes
   its agent session; every other node always starts clean.
   - **Resume** (`resume_run_dir` set): `ArtifactWriter.resume` re-binds the writer; a missing
     [`checkpoint.json`](../run-artifacts.md#checkpointjson), or one whose `current_id` isn't in
     the (possibly-changed) graph, is a hard error (`1`). The context restarts from
     `{manifest, checkpoint["context"]}`. Then the idempotency check, `_should_fast_forward`
     (`main.py`): true iff the checkpointed node already has a
     [`done.json`](../run-artifacts.md#node-iddonejson) whose `seq` matches the checkpoint's `seq`
     and names a `next` — i.e. it finished but the cursor never advanced (killed in the gap).
     - **Fast-forward:** restore `ctx` from that node's `context_after.json` (falling back to the
       checkpoint context if absent) and jump `current_id` straight to `done["next"]` — the node's
       side effects (a git commit, a PROGRESS append) are never re-run.
     - **Otherwise:** re-enter `current_id` as-is and set `resume_interrupted_node = True` — the
       one case where the walk continues a node's Claude session rather than starting fresh.
   - **Fresh** (`resume_run_dir is None`): `ctx` seeds from
     `{manifest, graph.vars, params}` — `--params`/`--params-file` override the graph's own `vars`
     here, but only on a fresh start (a resume already has them baked into the checkpoint).
     `ArtifactWriter(graph.name, runs_dir, run_id=fresh_run_id)` creates a new run dir and
     `current_id = graph.start`.
6. `ctx.merge({"_run_dir": str(writer.run_dir)})` — every run's context carries its own run
   directory as a reserved key.
7. **Gas tank.** `_GasTank(_configured_gas())` constructs the run-wide
   [infinite-loop guard](gas-tank.md), shared across the top graph and every nested flow.
8. **Step the graph.** `_step_loop(graph, writer, ctx, current_id, resume_interrupted_node, …,
   tank=tank)` runs the shared [node-walk engine](#node-walk-engine) until a `terminal`/`fail`
   node, mutating `ctx` in place and returning the terminal node's `type`. This is the call that
   does the actual per-node work (checkpoint → dispatch by node type → merge outputs → write the
   step artifact → advance) — `run` itself never inspects individual nodes.
9. **Exit paths.** `run` catches exactly three exceptions escaping the walk, each terminating the
   in-flight agent subprocess first (`agent_runner.terminate_active()`) so nothing is left
   running:
   - `KeyboardInterrupt` — prints a paused/resume message and exits the **process** with code `130`
     (not a `return`); the run dir is left mid-checkpoint, ready to resume.
   - `OutOfGasError` (raised by the [gas tank](gas-tank.md) when a cycle never makes progress) —
     prints the diagnostic, marks `writer.finish(terminal="fail")`, and returns `1`. The run dir is
     left intact for inspection.
   - `BackendInvocationError` (an agent turn the [resilience ladder](run-agent.md) couldn't
     recover, or one that exhausted its budget with defaulting disabled) — prints a
     transient/non-recoverable message plus a resume command, marks
     `writer.finish(terminal="fail")`, and returns `1`.
   - Any other exception (a script node's own uncaught error, propagated by `_step_loop`) is
     **not** caught here: it escapes `run` uncaught and crashes the process. `run`'s fail-soft
     guarantee covers `agent` nodes and the gas-tank/interrupt paths; a `script` node's own bug is
     not defaulted past.
   - **On success** (the walk returns normally): `writer.write_final_context(ctx.as_dict())` then
     `writer.finish(terminal=terminal_type)` record the terminal snapshot; returns `0` for a
     `terminal` node, `1` for a `fail` node.

**Resume is in-place and automatic.** Each `(workflow, run-id)` maps to one stable run dir (step
4); an existing checkpoint resumes from the checkpointed node with its saved context,
fast-forwarding past a node that already finished (step 5). Delete the dir to start over.

## Node-walk engine

The engine [`run`](#execution) (step 8) and [`run_flow`](run-flow.md) both call to actually walk a
graph one node at a time: `while True`, step the current node, follow its `next`, repeat until a
`terminal`/`fail` node is reached. It has no awareness of *which* graph it's walking — root or
nested flow — so `run` and `run_flow` share one implementation instead of duplicating the dispatch
logic.

- code: `workhorse/workhorse/main.py::_step_loop`

**Per-step shape**, before the type-specific dispatch below:

1. **Terminal check first.** If the current node is a `TerminalNode` (covers both `terminal` and
   `fail` — the config-level distinction lives in `node.type`), return `node.type` immediately —
   no burn, no checkpoint, nothing written for the terminal node itself.
2. **Burn.** [`tank.burn(current_id)`](gas-tank.md#burnnode_id) — spends one unit of the shared
   [gas tank](gas-tank.md), raising `OutOfGasError` if a cycle never refuels.
3. **Checkpoint.** [`writer.write_checkpoint(current_id, ctx.as_dict())`](artifact-writer.md#write_checkpointcurrent_id-context)
   — records the node about to run *before* it runs, so a crash mid-node still leaves a valid
   prior checkpoint to resume from.
4. **Dispatch by `isinstance(node, …)`** — see below, one branch per node type.

**Dispatch, by node type:**

- **`AgentNode`** — runs [`run_agent`](run-agent.md#the-ladder) with `resume_session=True` only
  when `resume_interrupted_node` is `True` for *this exact* node (the one case where the walk
  continues a prior Claude session rather than starting fresh); `resume_interrupted_node` is then
  reset to `False` so no later node in the same walk mistakenly resumes. On success,
  `ctx.merge(outputs)` then [`writer.write_step(...)`](artifact-writer.md#write_stepnode_id-prompt-output-context_after-next_nodenone)
  records the artifact and advances `current_id = node.next`; a missing `next` is a `RuntimeError`
  (`"agent node '<id>' has no next"`). A `BackendInvocationError` escaping `run_agent` (the
  [resilience ladder](#resilience-fail-soft) exhausted) is logged and re-raised — `_step_loop`
  itself does no recovery, it only propagates for `run` to catch.
- **`ScriptNode`** — runs `run_script`, resets `resume_interrupted_node` to `False` (a script node
  is never resumed mid-session — it has no session), then the same
  `ctx.merge(outputs)` → `write_step` → advance-to-`next` shape as `AgentNode` (missing `next` is
  the same `RuntimeError` shape). If the node declares a `refuel:` dot-path,
  [`tank.refuel(current_id, ctx.get_dotpath(...))`](gas-tank.md#refuelnode_id-value) runs after the
  merge, so the tank sees the *post-step* value. Exceptions: `ScriptExitError` (the script's own
  process exited non-zero) is caught and turned into `sys.exit(e.exit_code)` — this is the one
  dispatch branch that can terminate the whole process directly rather than propagating up through
  `run`; any other `Exception` is logged and re-raised, same as `AgentNode`.
- **`CallNode`** — runs `run_call`, resets `resume_interrupted_node` to `False`, then the same
  `ctx.merge(outputs)` → `write_step` → advance shape, including the same `refuel:` handling as
  `ScriptNode` (a `call` node can also declare `refuel:`). No dedicated exception handling — any
  error `run_call` raises propagates straight out of `_step_loop` uncaught.
- **`BranchNode`** — runs `evaluate(node, ctx)`, resets `resume_interrupted_node` to `False`, then
  [`writer.write_branch(current_id, path, value, next_node)`](artifact-writer.md#write_branchnode_id-path-value-next_node)
  and advances `current_id = next_node`. A branch always has a route (`cases`/`conditions` fall
  back to `default`), so unlike the other branches there is no missing-`next` guard here. No
  dedicated exception handling.
- **`FlowNode`** — the one branch that captures `resume_interrupted_node` into a local
  `is_flow_resume` **before** resetting it to `False`, because a flow-node resume must distinguish
  "the parent process was killed while inside this flow" (continue the child walk from its own
  checkpoint) from "a loop body is re-invoking the same flow node fresh" (start the child clean) —
  seen `run_flow`. Calls [`run_flow`](run-flow.md) with `depth + 1` and that `is_flow_resume` flag;
  `run_flow`'s returned outputs are merged into `ctx` the same way as the other node types, then
  `write_step` and advance to `node.next` (same missing-`next` `RuntimeError` as `AgentNode`). No
  dedicated exception handling — a `run_flow` error (including a nested `OutOfGasError` or
  `BackendInvocationError`) propagates straight out, since the gas tank and agent resilience are
  shared across the flow boundary rather than re-scoped per nesting level.
- **Unknown node type** — `isinstance` falls through every branch above → `RuntimeError(f"Unknown
  node type: {type(node)}")`. Reachable only if the `Graph`'s node union is extended without a
  matching dispatch branch here.

`depth` (the flow-nesting counter [`run_flow`](run-flow.md) enforces `_MAX_FLOW_DEPTH` against) is
threaded through `_step_loop` only to pass to `run_flow` on a `FlowNode` step — every other branch
ignores it.

## Resilience (fail-soft)

Because runs go unattended for days, an `agent` node never crashes the run; it escalates a ladder
([`run_agent`](run-agent.md)) before advancing:

1. **Transient retry** — rate limits, timeouts, network blips, empty results retry with backoff.
   Scheduled-reset caps (spending/usage/session/quota) are *waited out* to their reset, then retried.
2. **Compact & continue** — on context-window overflow, `/compact` the node's session and retry the
   *same* prompt, preserving progress.
3. **Reframe** — on persistent invocation/parse failure, re-ask from scratch in a fresh session,
   simplifying each attempt.
4. **Default to next** — when reframing is exhausted, emit each output's declared
   `OutputSpec.default` (null if unset) and advance to `next`, so the run continues. Disable with
   `AGENT_USE_DEFAULT_OUTPUTS=false` to hard-fail instead.

Related: [load_workflow](load-workflow.md) (parsing), [AgentBackend](agent-backend.md) (the harness),
[run_agent](run-agent.md) (the resilience ladder in full), [workflow file format](../workflow-format.md)
(the on-disk shape).
