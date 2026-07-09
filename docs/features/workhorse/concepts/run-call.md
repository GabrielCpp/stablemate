---
type: concept
slug: run-call
title: run_call — invoke a builtin call node
---
# run_call — invoke a builtin call node

The handler the [node-walk engine](workflow.md#node-walk-engine)'s `CallNode` branch calls: looks
up a [`call`](../workflow-format.md#call) node's `fn` in the [builtins registry](builtins-registry.md)
and invokes it with rendered `args` — a lightweight step with no LLM and no subprocess.

- code: `workhorse/workhorse/runner/call.py::run_call`
- verify: `workhorse/tests/test_call_node.py::test_call_node_end_to_end`

## Contract

- **Input:**
  - `node: CallNode` — supplies `node.fn` (the [registry](builtins-registry.md) key), `node.args`
    (Jinja2 template strings, keyword-rendered), and `node.outputs`
    (`list[CallOutputSpec]` — see [`OutputSpec`](../workflow-format.md#outputspec)).
  - `ctx: WorkflowContext` — rendered via [`as_dict()`](workflow-context.md#as_dict---dict) once,
    the base every `render_string` call in this function renders `node.args` against.
  - `workflow_dir: Path` — accepted for signature parity with [`run_script`](run-script.md) /
    [`run_agent`](run-agent.md); unused by the function body.
- **Output:** `(label, outputs)` — `label: str` is a synthetic node label (there is no rendered
  prompt/command for a `call` node, so this is what's written to the run artifact in their place);
  `outputs: dict[str, Any]` is one entry per `node.outputs` spec.
- **Raises:** `RuntimeError(f"CallNode '{node.id}': unknown built-in '{node.fn}'. Available:
  {sorted(REGISTRY)}")` when `node.fn` isn't a [registry](builtins-registry.md) key. Otherwise
  propagates whatever the looked-up builtin raises; no dedicated exception handling of its own.

## Algorithm

1. **Resolve the builtin.** `fn = REGISTRY.get(node.fn)` — look up `node.fn` in the
   [builtins registry](builtins-registry.md); raise `RuntimeError` (see Raises above) if absent.
2. **Render the context once.** `ctx_dict = ctx.as_dict()`.
3. **Render `args`.** `rendered_args = {k: render_string(v, ctx_dict) for k, v in node.args.items()}`
   — each `node.args` value is rendered as its own inline Jinja2 template (unlike
   [`run_script`](run-script.md#algorithm)'s positional list, this stays a `dict` since builtins
   take keyword arguments).
4. **Invoke.** `raw_result = fn(**rendered_args)` — calls the resolved builtin with the rendered
   args as keyword arguments; whatever it returns (or raises) passes straight through.
5. **Build the label.** `label = f"call:{node.fn}({', '.join(f'{k}={v!r}' for k, v in
   rendered_args.items())})"` — e.g. `call:incr(value='4')` — a human-readable record of what ran,
   written to the run artifact in place of a rendered prompt/command.
6. **Wrap outputs per spec.** For each `spec` in `node.outputs` (`CallOutputSpec`): if
   `spec.wrap` is set, `outputs[spec.key] = {spec.wrap: raw_result}` (nests the scalar result under
   that key, e.g. `{"value": 5}`); otherwise `outputs[spec.key] = raw_result` (the bare scalar). Every
   spec wraps the **same** `raw_result` — a `call` node has one return value, fanned out to as many
   context keys as `outputs` declares.
7. **Return** `(label, outputs)`.

## Consumers

- The [node-walk engine](workflow.md#node-walk-engine) (`workhorse/workhorse/main.py::_step_loop`)
  — the only caller, once per `CallNode` step. On success it merges `outputs` into the
  [`WorkflowContext`](workflow-context.md#mergedata---none), refuels the
  [gas tank](gas-tank.md#refuelnode_id-value) if `node.refuel` is set, writes the step artifact
  (`label` in place of a rendered prompt/command), and advances to `node.next`.
