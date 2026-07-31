---
type: concept
slug: workflow-context
title: WorkflowContext — the prompt render bag
---
# WorkflowContext — the prompt render bag

The key→value bag one agent turn's Jinja prompt renders against. The engine builds a fresh one
per [`self.agent(...)`](../workflow-format.md#the-agent-turn) call — the repo's
[context manifest](../context-manifest.md) underneath, that call's arguments on top — and
[`run_agent`](run-agent.md) unwraps it with `as_dict()` to get the render base. It is deliberately
a thin wrapper (a plain `dict` plus dotted-path traversal) that knows nothing about states, nodes,
outputs or checkpoints.

**It is not `self.ctx`, and the name collision is the one trap on this page.** A `Workflow`'s
`self.ctx` is whatever object that workflow's `setup()` returned — the run's derived, immutable
middle tier, restored from the checkpoint on resume (see
[`drive`](pyflow-driver.md#the-three-tiers-of-state-and-no-fourth)). `WorkflowContext` is not that
and never sees it. Under the retired YAML engine the two were the same idea — this bag *was* the
graph walk's live state, merged into after every node and snapshotted into
`checkpoint.json` — which is why it still carries the general-sounding name. Today the live state
lives on the workflow instance, and only the render base lives here.

- code: `workhorse/workhorse/context.py::WorkflowContext`
- verify: `workhorse/tests/test_agent_recovery.py::test_rendered_prompt_is_written_and_only_path_is_printed`

It sits at the package top level rather than under a driver subpackage on purpose: the agent
runner takes one, and the runner is shared. The graph walk was only ever its first caller.

## State

- `_data: dict[str, Any]` — the only instance state; every method reads or mutates this one dict.

## `__init__(initial=None)`

Copies `initial` (or `{}` if `None`) into a fresh `_data` dict — the constructor never aliases the
caller's dict, so later mutation of the object passed in doesn't leak into the context (and vice
versa).

The engine's one construction site is `pyflow/engine.py`'s `self.agent` implementation:

```python
WorkflowContext({**self.env.manifest, **jsonable(args)})
```

Manifest first, the state's own arguments second, so a state that binds `repo` means its own and
not the manifest's. `jsonable` is what lets a state pass real Python objects (a `Path`, a pydantic
model, an `int`) instead of the Jinja template *strings* the YAML `args:` block was limited to.

## `merge(data) -> None`

`self._data.update(data)` — shallow dict update; a key in `data` overwrites the same key in
`_data`, and nested dicts are replaced wholesale rather than deep-merged.

**No caller remains in this repo.** Its callers were the graph walk (folding a node's declared
`outputs` into the running context) and the run-start `_run_dir` injection, both retired with the
YAML engine. A per-turn bag built and discarded inside one `self.agent` call has nothing to fold.

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
given at all".

**No caller remains in this repo.** The guardrail this primitive existed for was the `branch`
node's: it read `get_dotpath(node.path, default=<sentinel>)` and routed to the node's `default`
successor on a miss rather than raising, so a branch survived an upstream step returning an
unexpected shape. A Python state decides its own next state in ordinary Python, so there is no
path string to resolve and nothing to guard.

## `has_dotpath(path) -> bool`

`get_dotpath(path, default=<local sentinel>) is not <local sentinel>` — true iff `path` resolves to
some value (including a falsy one like `0`/`""`/`None` actually stored at that key). Also has no
caller left in this repo.

## `as_dict() -> dict`

`dict(self._data)` — a shallow copy of the whole bag, and the **only** method with a live caller.
`runner/agent.py::run_agent` opens with `ctx = context.as_dict()` and renders the node's prompt
against that dict. The copy is what stops the runner mutating the bag the engine handed it.

## `__repr__() -> str`

`f"WorkflowContext({self._data!r})"` — the whole bag, for debugging/log output.

## Consumers

- `pyflow/engine.py` — constructs one per `self.agent` call from `{manifest, args}`. The sole
  producer.
- [`run_agent`](run-agent.md) — `as_dict()` as the Jinja render base. The sole consumer.
- [`render_prompt`](render-prompt.md) — renders against that dict, with `ResilientUndefined` so a
  missing key renders empty and warns instead of aborting the turn.
