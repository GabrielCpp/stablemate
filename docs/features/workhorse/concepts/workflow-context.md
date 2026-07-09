---
type: concept
slug: workflow-context
title: WorkflowContext — the graph-walk context bag
---
# WorkflowContext — the graph-walk context bag

The key→value bag that carries a [workflow](workflow.md) run's live state across its whole
[execution](workflow.md#execution): every node's rendered Jinja `args`, a `branch` node's `path`
lookup, and the [run artifacts](../run-artifacts.md) snapshots
([`checkpoint.json`](../run-artifacts.md#checkpointjson)'s `context` field,
`<node-id>/context_after.json`, and the final `context.json`) all read or write through it. It is
deliberately a thin wrapper — a plain `dict` plus dotted-path traversal — with no notion of nodes,
outputs, or the graph; [`run`](../workhorse.md#run) owns the higher-level protocol (merging a
node's declared outputs in, deciding what seeds the initial dict from the
[context manifest](../context-manifest.md) and `vars`).

- code: `workhorse/workhorse/graph/context.py::WorkflowContext`
- verify: `workhorse/tests/test_branch_guardrail.py::test_get_dotpath_default_vs_raise`

## State

- `_data: dict[str, Any]` — the only instance state; every method reads or mutates this one dict.

## `__init__(initial=None)`
Copies `initial` (or `{}` if `None`) into a fresh `_data` dict — the constructor never aliases the
caller's dict, so later mutation of the object passed in doesn't leak into the context (and vice
versa). [`run`](../workhorse.md#run) constructs a new `WorkflowContext` at each of three points:
a fresh start (`{**manifest, **graph.vars, **params}`), a checkpoint resume
(`{**manifest, **checkpoint["context"]}`), and a fast-forward past an already-done node
(`{**manifest, **context_after}`) — in each case the manifest is re-merged as the base layer so a
resumed run still has the repo's [context manifest](../context-manifest.md) values available.

## `merge(data) -> None`
`self._data.update(data)` — shallow dict update; a key in `data` overwrites the same key in
`_data`, nested dicts are replaced wholesale (not deep-merged). Called once per node by
[workflow execution](workflow.md#execution) to fold a node's declared `outputs` into the running
context, and once at run start to inject the reserved `_run_dir` key (the writer's run directory,
as a string) so a prompt or script can reference its own run path.

## `get_dotpath(path, default=_MISSING) -> Any`
Resolves a dot-separated path (e.g. `"analysis.status"`) by walking `_data` one segment at a time.
Algorithm:
1. Split `path` on `.`; start `value = self._data`.
2. For each segment: if `value` isn't a `dict`, or the segment isn't a key in it, the path is
   unresolvable — go to step 3. Otherwise `value = value[segment]` and continue.
3. **Unresolvable case:** if a `default` was supplied (any value other than the private
   `_MISSING` sentinel), return it. Otherwise raise `KeyError` — with a message distinguishing "not
   a dict at this point" (`Cannot traverse '<part>' in non-dict value at path '<path>'`) from "key
   absent" (`Key '<part>' not found (path: '<path>')`).
4. If every segment resolved, return the final `value`.

`_MISSING` (a module-level `object()` sentinel, not `None`) is what lets a caller legitimately pass
`default=None` and still get `None` back for a truly-missing path, distinct from "no default was
given at all". This is the primitive [`branch` node evaluation](workflow.md#node-types)
(`workhorse/workhorse/runner/branch.py::evaluate`) builds its guardrail on: it calls
`get_dotpath(node.path, default=_UNRESOLVED)` with its own local sentinel and routes to the node's
`default` next-node on a miss instead of raising, so a branch survives an upstream step returning an
unexpected shape.

## `has_dotpath(path) -> bool`
`get_dotpath(path, default=<local sentinel>) is not <local sentinel>` — true iff `path` resolves to
some value (including a falsy one like `0`/`""`/`None` actually stored at that key). Used to guard a
lookup without a `try`/`except KeyError`.

## `as_dict() -> dict`
`dict(self._data)` — a shallow copy of the whole bag. This is the seam every consumer that needs the
full context (rather than one dot-path) goes through, so none of them can accidentally mutate the
context out from under the graph walk:
- [`run`](../workhorse.md#run)'s [execution loop](workflow.md#execution) — passes it to
  `ArtifactWriter.write_checkpoint`/`write_step`/`write_final_context` for every
  [run-artifact](../run-artifacts.md) snapshot, and to `render_string` for a `flow` node's `args`.
- `runner/agent.py::run_agent` — the base dict Jinja renders the agent prompt against.
- `runner/script.py::run_script` — the base dict Jinja renders a script node's args against.
- `runner/call.py::run_call` — the base dict Jinja renders a `call` node's args against.
- `graph/dot.py` (`workhorse dot`) — seeds a throwaway `WorkflowContext` from `--pin` values purely
  to reuse `runner/branch.py::evaluate`'s routing logic when pruning the diagram.

## `__repr__() -> str`
`f"WorkflowContext({self._data!r})"` — the whole bag, for debugging/log output.

## Consumers

- [Workflow execution](workflow.md#execution) — constructs, `merge`s, checkpoints, and finalizes
  the context across the node loop; a `flow` node's child context is a fresh `WorkflowContext` seeded
  from `{manifest, flow.vars, rendered_args}`, isolated from the parent's.
- `runner/branch.py::evaluate` — the sole `get_dotpath`/guardrail consumer among the node runners.
- `runner/agent.py::run_agent`, `runner/script.py::run_script`, `runner/call.py::run_call` — each
  takes `as_dict()` as the Jinja render base for its prompt/command/call args.
- [`run-artifacts.md`](../run-artifacts.md) — `checkpoint.json`'s `context`,
  `<node-id>/context_after.json`, and `context.json` are all `as_dict()` snapshots written by
  `ArtifactWriter`.
- `graph/dot.py` (`workhorse dot --pin`) — builds a one-off `WorkflowContext` from pinned values to
  evaluate branch routing when pruning the rendered diagram.
