# pyflow

Workflows written as Python state machines. A workflow's states are methods of a `Workflow` subclass, and its nodes are functions on a blueprint.

## Map

- `activity.py`: the `activity` label, taken from the last log line flagged as what the run is doing.
- `blueprint.py`: node libraries a workflow composes, and what registration records about each node.
- `dot.py`: the Graphviz DOT rendering of a flow graph.
- `driver.py`: the loop that steps a workflow from state to state, and checkpoints each move.
- `engine.py`: what `self.call`, `self.agent`, `self.handoff` and `self.output` do inside a state, including their dry-run stand-ins.
- `errors.py`: every error the Python workflow driver raises.
- `graph.py`: the state graph read off a workflow's source.
- `names.py`: the name index that maps live and retired state and node names to their targets.
- `park.py`: blocking a run on an Await's file until it is answered, over the file and the control socket, and writing the ask.
- `preflight.py`: what a static read of a flow graph shows is wrong before a run starts.
- `registry.py`: the module-level object a console script points at: flows, nodes and the entry point.
- `run.py`: one run from its CLI invocation to an exit code: run dir, worktree dispatch, live reload and failure handoff.
- `transitions.py`: the three ways a state ends: `Continue`, `Done` and `Await`.
- `workflow.py`: the `Workflow` base class and the `state` decorator.
- `worktree.py`: cutting the fresh branch and git worktree a `--worktree` run dispatches into.
