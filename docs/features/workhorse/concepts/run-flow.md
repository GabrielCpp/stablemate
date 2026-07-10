---
type: concept
slug: run-flow
title: run_flow — call a named flow as a child graph
---
# run_flow — call a named flow as a child graph

The handler the [node-walk engine](workflow.md#node-walk-engine)'s `FlowNode` branch calls: runs
the named [flow](workflow.md#flows) as an isolated child [`Graph`](workflow.md), in its own
[`ArtifactWriter`](artifact-writer.md#subscopenode_id-flow_name-resumefalse---artifactwriter) subscope, sharing the
same [gas tank](gas-tank.md) as the parent walk, and returns the child's declared outputs to merge
into the caller's context.

- code: `workhorse/workhorse/main.py::_run_flow`

## Contract

- **Input:** the `FlowNode`, the parent `Graph` and [`ArtifactWriter`](artifact-writer.md), the
  parent [`WorkflowContext`](workflow-context.md), the shared [gas tank](gas-tank.md), the current
  nesting `depth`, and `is_flow_resume` — the [node-walk engine](workflow.md#node-walk-engine)'s
  "was the parent process killed inside this exact flow node" signal, captured *before* the engine
  resets its resume flag (not "does a checkpoint happen to exist" — a flow that already ran to
  completion also leaves one behind).
- **Output:** the child graph's declared outputs, read back off the child's final
  `WorkflowContext` once its own [node-walk](workflow.md#node-walk-engine) reaches a terminal node.
- **Raises:** `RuntimeError` if `depth + 1` exceeds `_MAX_FLOW_DEPTH` — a flow-nesting cycle guard,
  independent of the [gas tank](gas-tank.md)'s per-step guard, and any exception the child's node
  walk itself raises (an `OutOfGasError`, a `BackendInvocationError`, an unhandled script error),
  which propagates straight out to the caller rather than being caught here.

## Algorithm

1. **Depth guard.** If `depth + 1 > _MAX_FLOW_DEPTH` (16 — a runaway-nesting backstop, not a design
   limit), raise `RuntimeError("flow nesting exceeded depth 16 at flow node '<id>' (flow
   '<name>') — likely a flow cycle")`.
2. **Resolve the flow.** `flow = graph.flows[node.name]` — the name is validated to exist in the
   containing graph's `flows:` map at [load time](load-workflow.md), so no existence check here.
3. **Render `args` against the parent.** `rendered = {k: render_string(v, parent_ctx.as_dict())
   for k, v in node.args.items()}` — each `FlowNode.args` value is a Jinja2 template rendered
   against the **parent's** context; the rendered strings are the only thing that crosses the
   parent/child boundary (alongside the flow's own `vars`), keeping it explicit.
4. **Log.** Prints `[workhorse] flow   → <node.id> (<node.name>)`.
5. **Open a nested artifact scope.** `child_writer = writer.subscope(node.id, flow.name,
   resume=resume)` —
   [`ArtifactWriter.subscope`](artifact-writer.md#subscopenode_id-flow_name-resumefalse---artifactwriter)
   roots the child run under `<run_dir>/<node.id>/_flow`; `resume` is `_run_flow`'s own `resume`
   parameter — the caller's "was the parent process killed *inside this exact flow node*" signal,
   never mere checkpoint presence.
6. **Seed the child's initial context.** `initial = {**manifest, **flow.vars, **rendered}` — the
   [context manifest](../context-manifest.md) as the outer layer, then the flow's own `vars`
   (its declared parameter defaults), then the rendered `args` on top — so an explicit `arg`
   always wins over the flow's own default.
7. **Decide resume vs. fresh for the child.** `current_id, child_ctx, resume_interrupted_node =
   _enter(child_writer, flow, manifest, initial)` (`workhorse/workhorse/main.py::_enter`) —
   reads `child_writer.read_checkpoint()`:
   - **No checkpoint** → fresh start: `(flow.start, WorkflowContext(initial=initial), False)`.
   - **Checkpoint present** → validates its `current_id` is still a node in `flow` (else
     `ValueError(f"checkpoint node '<id>' not found in flow '<flow.name>' (did the flow
     change?)")`), rebuilds `child_ctx = WorkflowContext(initial={**manifest,
     **checkpoint["context"]})`, then runs the **same** fast-forward idempotency check as
     [`run`](workflow.md#execution)'s inline resume logic (`_should_fast_forward` — the
     checkpointed node's `done.json` seq matches the checkpoint's seq and names a `next`):
     fast-forward restores `child_ctx` from that node's `context_after.json` (falling back to
     the checkpoint context if absent) and jumps `current_id` to `done["next"]` with
     `resume_interrupted_node=False`; otherwise it re-enters the checkpointed `current_id` as-is
     with `resume_interrupted_node=True` — the one case where the child walk continues that
     node's Claude session instead of starting clean. `_enter` is the same decision `run()`
     inlines for the root graph (kept separate there only for its root-specific log messages),
     factored out here so a `flow` node can reuse it across its own nested boundary.
8. **Walk the child graph.** `term = _step_loop(flow, child_writer, child_ctx, current_id,
   resume_interrupted_node, manifest=manifest, workflow_dir=workflow_dir,
   session_id_path=child_writer.run_dir / ".session_id", tank=tank, depth=depth + 1)` — the same
   [node-walk engine](workflow.md#node-walk-engine) the root graph uses, given the child's own
   `.session_id` path (scoped under the child's run dir, never the parent's) and the **same**
   shared `tank` (the [gas tank](gas-tank.md) budgets progress across the whole run, not per
   nesting level) and `depth + 1` (so a nested flow's own `flow` nodes are checked against the
   same depth ceiling). Runs until `flow` reaches a `terminal`/`fail` node; any exception the walk
   raises (`OutOfGasError`, `BackendInvocationError`, an unhandled script error) propagates
   straight out of `_run_flow` uncaught.
9. **Finalize the child run.** `child_writer.write_final_context(child_ctx.as_dict())` then
   `child_writer.finish(terminal=term)` —
   [writes](artifact-writer.md#write_final_contextcontext) the child's final context snapshot and
   [marks](artifact-writer.md#finishterminal) its `run.json` terminal, exactly like the root
   graph does at the end of [`run`](workflow.md#execution).
10. **Lift the declared outputs.** Returns `{spec.key: child_ctx.get_dotpath(spec.key,
    spec.default) for spec in node.outputs}` — reads each `FlowNode.outputs` key out of the
    child's *final* `WorkflowContext` by dot-path, falling back to that `OutputSpec`'s declared
    `default` when the key is absent; mirrors the same output-lookup contract an `agent`/`script`
    node uses for its own `outputs`.

## Consumers

- The [node-walk engine](workflow.md#node-walk-engine) (`workhorse/workhorse/main.py::_step_loop`)
  — the only caller, once per `FlowNode` step, passing its captured `is_flow_resume` as `resume`.
