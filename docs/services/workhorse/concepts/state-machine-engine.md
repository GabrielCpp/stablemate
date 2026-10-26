---
type: concept
title: State-machine engine
---
# State-machine engine

A workflow is a Python class whose public methods are its states. The engine walks the class one
state at a time, checkpointing between states, so a run that dies resumes at the state it was in.
The walk starts at the state named `start` unless the class names another.

A state ends in exactly one of three transitions:

- `Continue(result, next, ...)` steps to the state `next` with the arguments given. The arguments
  are bound against `next`'s own signature, so a mismatch fails at the transition, not later. A
  state may not declare `*args` or `**kwargs`, because its parameters are its checkpoint.
- `Done(result)` ends the walk, and the run records the terminal outcome.
- `Await(path, questions, next, ...)` checkpoints and parks the run until the file at `path` is
  answered, as described in [operator inbox](operator-inbox.md).

Any transition can carry `.because(reason)`, a sentence the run logs beside it.

Inside a state, a workflow does its work through four calls:

- `call(node, ...)` runs a blueprint node, which is a plain function from a node library.
- `agent(prompt, returns=...)` renders a prompt and runs one agent turn, as described in
  [agent turns](agent-turns.md). An inline prompt carries a `label` matching
  `^[a-z0-9][a-z0-9_-]*$`.
- `handoff(flow, ...)` drives another workflow to completion and returns its result.
- `output(node)` returns the recorded output of a node that already ran.

A work list gives a run one shared backlog of items to claim, settle and count. `pipeline` drains a
kind of the run's work list into a flow or a state, a chunk per state visit, so every chunk is a
resume point. Draining into a state settles each row to `done` right after its `handoff`, inside
the same `pipeline` call. Draining into a flow defers settlement: the chunk it dispatched settles
only at the start of the next fresh (non-resuming) visit, just before that visit claims its own
chunk. A row claimed more than three times is blocked.

States and nodes share one name index. A renamed state keeps its old name as an alias, so a run
checkpointed under the old name still resumes. A name that resolves to nothing fails with the list
of known states.

Before a run starts, preflight reads the flow's graph off its source and refuses it when the
start state does not exist, when no state returns `Done`, when a transition names something that
is not a state, when a state is unreachable from the start, or when a prompt file is missing. A
prompt path that comes from a helper marked `@resolves_prompt` is read through that helper, and
a local bound to a ternary of two such calls is read arm by arm, each arm resolved the same way.
Any other computed path is reported, because a path preflight cannot read is a path nothing
checks. The same graph renders to Graphviz DOT through [`dot`](../workhorse.md#dot), and the
[check a workflow](../flows/check-workflow.md) journey renders one.

- code: `workhorse/workhorse/pyflow/workflow.py::Workflow` @9704358a90e7
- code: `workhorse/workhorse/pyflow/workflow.py::state` @9704358a90e7
- code: `workhorse/workhorse/pyflow/transitions.py::Continue` @05edc5a834cc
- code: `workhorse/workhorse/pyflow/transitions.py::Done` @05edc5a834cc
- code: `workhorse/workhorse/pyflow/transitions.py::Await` @05edc5a834cc
- code: `workhorse/workhorse/pyflow/engine.py::Engine` @922a7b361e6e
- code: `workhorse/workhorse/pyflow/driver.py::drive` @6ee79b75b0f1
- code: `workhorse/workhorse/pyflow/driver.py::coerce_params` @6ee79b75b0f1
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph` @103855581ca1
- code: `workhorse/workhorse/pyflow/names.py::NameIndex` @ec28548d30de
- code: `workhorse/workhorse/pyflow/blueprint.py::Blueprint` @4911263291b8
- code: `workhorse/workhorse/pyflow/preflight.py::preflight` @3460fa12f550
- code: `workhorse/workhorse/pyflow/errors.py::PyflowError` @6daae074220e
- code: `workhorse/workhorse/pyflow/errors.py::UnknownStateError` @6daae074220e
- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog` @fc149a498518
- code: `workhorse/workhorse/pyflow/__init__.py` @85a539ba0108
- code: `workhorse/workhorse/pyflow/README.md` @c504bb5519c2
- code: `workhorse/workhorse/worklist.py::WorkList` @5527e3514bc3
- code: `workhorse/workhorse/context.py::WorkflowContext` @313726f99d8a
- code: `workhorse/docs/WORKFLOW.md` @7ac0edfa642f
- code: `workhorse/docs/AUTHORING.md` @83e8becee436
