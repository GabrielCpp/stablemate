---
type: concept
slug: pyflow-driver
title: drive — walk a workflow written as a Python state machine
---
# drive — walk a workflow written as a Python state machine

The loop workhorse runs. There is one engine and this is it: `drive` calls a *method* on a
`Workflow` instance and follows the transition it returns, checkpointing before each one.
Control flow is ordinary Python — `if`, `for`, a counter that is just a counter — because the
graph lives in the method bodies rather than in a data file the engine interprets.

The retired YAML front-end advanced a cursor over a declared node graph and merged each node's
outputs into an ambient context map; what replaced it is [the three tiers of
state](#the-three-tiers-of-state-and-no-fourth) below. Everything *under* the state — the runs
directory and [`ArtifactWriter`](artifact-writer.md) layout, the [agent
backends](agent-backend.md), telemetry, and the [resilience ladder](run-agent.md) — is
unchanged by that, which is why a ported workflow's operator knobs still mean what they meant.

- code: `workhorse/workhorse/pyflow/driver.py::drive`

## Contract

- **Input:** a `Workflow` instance (its class fields already populated from `--params`), a
  `RunEnv` (the [`ArtifactWriter`](artifact-writer.md), the workflow directory, the session-id
  path, the [`RunConfig`](config.md), and the `dry_run` / `deadline` flags), and an optional
  `Resume` read off a checkpoint.
- **Output:** whatever the terminal `Done(result)` carried. A `handoff` caller receives exactly
  this value.
- **Raises:** `WorkflowFailed` — from a state that raises it, from a state that returns something
  that is not a transition, when the transition budget is exhausted, or when a checkpoint's
  parameters will not coerce; `UnknownStateError` when a checkpoint names a state the class no
  longer has; `WorkflowFrozenError` when a state assigns to the instance; `RunBudgetExceeded`
  when `deadline` passes between states.

## Algorithm

1. **Seal the instance.** On a fresh start, call `setup()` once and pass its return to
   `_seal(ctx)`, which sets `self._ctx` and flips the freeze. On a **resume**, `setup()` is *not*
   re-run — the recorded `ctx` is revived from the checkpoint and sealed instead, because a
   `setup()` that reads the world would otherwise re-read a world that has moved.
2. **Resolve the state.** `type(wf).resolve_state(name)` walks the class's `NameIndex`: live
   names first, then `aliases=[…]`. A name matching neither raises `UnknownStateError` naming the
   known states and the fix, rather than falling back to `start` — silently restarting a
   week-long run is the worse failure.
3. **Coerce the parameters.** A resumed state's parameters arrive as JSON. Each is run through a
   pydantic `TypeAdapter` built from the state's own annotation, so a `Path` checkpointed as a
   string comes back a `Path`.
4. **Checkpoint, then act.** `write_state_checkpoint(state, params, inputs=…, ctx=…,
   waiting_on=…)` is written *before* the state body runs, so a crash inside the body resumes into
   the same state rather than past it.
5. **Dispatch on the return value.** `Done` ends the loop; `Continue` binds its keyword arguments
   against the target's signature and loops; `Await` writes the questions, checkpoints with
   `waiting_on` set, and polls. Anything else is a `WorkflowFailed` — a state that falls off the
   end returning `None` is a bug, not a terminal.
6. **Budget.** Each hop burns one unit of `max_transitions` (`WORKHORSE_MAX_TRANSITIONS`,
   default 1000). Exhaustion raises `WorkflowFailed`. A workflow that declares
   `REFUEL_ON = {"<param>"}` refills that budget to full whenever the named state parameter
   takes a new value, so what the count bounds is transitions *since the last forward step* —
   a drain's backlog stops being a number the operator must have predicted, while a
   ping-pong between two states, where the parameter never moves, still dies on the same
   1000. That, plus the wall-clock
   `WORKHORSE_MAX_RUNTIME_S` deadline checked between states, is the whole runaway bound —
   there is no per-node fuel budget, because a Python `for` loop is not a cycle in a graph.

## The three tiers of state, and no fourth

| Tier | Written by | Lives for | Reached as |
|---|---|---|---|
| Inputs | the CLI (`--params`) | the whole run | `self.<field>` |
| `self.ctx` | `setup()`, once | the whole run | `self.ctx` |
| State parameters | the previous state | one hop | the state's own arguments |

The rule is **if a state writes it, it is a parameter of the next state.** Everything a resume
needs is therefore in the checkpoint by construction, which is why the instance freezes once
`setup()` returns: an assignment from inside a state would produce a value that survives in
memory but not on disk, and the run would behave differently after a reboot than before one.

`self.output(node)` is a read, not a fourth tier — it re-reads the node's recorded
`output.json` (latest invocation, re-validated into the node's declared return type) and raises
`NodeNotRunError` when the node has not run.

## Validation happens three times, on purpose

| Moment | Mechanism | Catches |
|---|---|---|
| Author time | the state's own annotations | a parameter with no type |
| Transition time | `inspect.signature(target).bind(**kw)` | `Continue(None, self.review, cont=1)` — the typo fails on the transition that made it |
| Resume time | pydantic `TypeAdapter` per parameter | a checkpoint written by an older signature |

## Resume is coarse, so states must be idempotent

There is no intra-state memo, no step key, and no per-callsite fingerprint. A resume re-enters
the checkpointed state **from the top** and re-runs everything in it. This is a deliberate trade:
fingerprinting callsites would make a state's resumability depend on the source line it sits on,
so an edit between crash and resume would silently change which work is skipped.

The contract a state body owes is therefore **idempotency, not determinism** — a state that
appends a row checks first, a state that commits is a no-op on a clean tree.

## Renaming a state without stranding a run

The checkpoint names a state, so a rename orphans every run checkpointed on the old name.
`aliases=[…]` — on `@workflow.state` and on `@blueprint.node` alike — is the pin:

- a checkpoint naming an unknown state fails loudly rather than starting over;
- declaring the old name as an alias resumes it;
- an alias colliding with a live name raises at **registration** (import), not at resume;
- `dot` and `--dry-run` render live names only, so an alias never appears as a second state.

Nodes carry aliases for the same reason at a different layer: `self.output(node)` resolves against
a run *directory* named after the node, so a renamed node would otherwise lose the output a
half-finished run already recorded.

## A checkpoint from the retired engine is refused, not misread

A checkpoint is tagged `"engine": "pyflow"`, and `read_resume` refuses anything else by name.
The YAML engine is gone, but the run directories it wrote are not: they sit in the same
`.agents/runs` tree and are eligible for the same `--resume-latest`. The failure this prevents
is not the `KeyError` — it is a `current_id` that collides with a state name by coincidence and
resumes the wrong thing. Such a run cannot be resumed; start it over.

## Related

- [the workflow format](../workflow-format.md) — the package shape this walks
- [state graph](pyflow-state-graph.md) — what `dot` and `--dry-run` derive from the same classes
- [ArtifactWriter](artifact-writer.md) — the run directory and checkpoint files it writes
- [`AgentRunner.run`](run-agent.md) — the resilience ladder `self.agent` goes through unchanged
