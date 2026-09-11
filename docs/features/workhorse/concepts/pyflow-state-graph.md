---
type: concept
slug: pyflow-state-graph
title: state_graph / preflight — the state machine read off its own source
---
# state_graph / preflight — the state machine read off its own source

What [`workhorse-<name> dot`](../workhorse.md#dot) draws and what
[`--dry-run`](../workhorse.md#run) checks for a workflow written as a Python state machine
(walked by [drive](pyflow-driver.md)). Nothing declares the graph: a transition is an
*expression a state returns*, so it is recovered by parsing each state's own source and reading
every `Continue` / `Await` / `Done` constructor found in it. (The retired YAML front-end had
nothing to derive — a node declared its `next:` and the renderer read the key back.)

Two properties follow, and they are the reason this is static rather than an execution trace:

- It **over-approximates**: both arms of an `if` become edges, because nothing here evaluates a
  condition.
- It **cannot drift** from the code, the way a hand-maintained `next=[…]` list can.

Enumerating paths by *running* the states buys neither. A state branching on `self.ctx` would
have to be fed fabricated values and would raise on the first comparison against a `--dry-run`
stand-in — so running the machine and reading it are two different tools here, deliberately:
execution covers the one path it takes, this covers every path.

Cost is `sum over states of (transitions in that state)` — linear in states, because a transition
is data the driver reads rather than a call it makes, so cross-state combinations are never
explored.

- code: `workhorse/workhorse/pyflow/graph.py::state_graph`
- code: `workhorse/workhorse/pyflow/graph.py::preflight`
- code: `workhorse/workhorse/pyflow/dot.py::to_dot`
- tests: [state graph tests](../../../../workhorse/tests/test_pyflow_graph.py)

## Methods

### FlowGraph.label
- sig: `label -> str`
- returns: slash-joined registered flow names, or the workflow class name when no names exist
- verify: json_path(path="$.label", equals="default")
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph.label`

### FlowGraph.state
- sig: `state(name: str) -> StateNode | None`
- returns: the live state node with the requested name, or `None` when the graph has no such node
- verify: count(subject="state lookup results in a graph", equals=1)
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph.state`

### FlowGraph.reachable
- sig: `reachable() -> set[str]`
- returns: states reachable from the start over non-dynamic, non-dangling edges
- verify: count(subject="reachable states in a two-state flow", equals=2)
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph.reachable`
- code: `workhorse/tests/test_pyflow_graph.py::test_a_target_the_source_cannot_name_is_reported_as_dynamic`
- tests: `workhorse/tests/test_pyflow_graph.py::test_a_target_the_source_cannot_name_is_reported_as_dynamic`

### FlowGraph.unreachable
- sig: `unreachable() -> tuple[str, ...]`
- returns: live states not reached by the static walk
- verify: count(subject="unreachable states in a connected flow", equals=0)
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph.unreachable`
- code: `workhorse/tests/test_pyflow_graph.py::test_reachability_finds_the_state_nothing_transitions_to`
- tests: `workhorse/tests/test_pyflow_graph.py::test_reachability_finds_the_state_nothing_transitions_to`

### FlowGraph.prompts
- sig: `prompts() -> tuple[tuple[str, str], ...]`
- returns: each live state and every literal agent prompt path found in that state
- verify: count(subject="literal prompts reported for a graph", equals=1)
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph.prompts`
- code: `workhorse/tests/test_pyflow_graph.py::test_node_calls_and_prompt_paths_are_collected`
- detail: [Seam collector selection](seam-collector-selection.md)
- tests: `workhorse/tests/test_pyflow_graph.py::test_node_calls_and_prompt_paths_are_collected`, `workhorse/tests/test_pyflow_graph.py::test_a_seam_inside_a_private_helper_is_attributed_to_the_state`

### state_graph
- sig: `state_graph(cls: type[Workflow], names=(), workflow_dir=None) -> FlowGraph`
- does: parses every live state source and records transitions and engine seams in source order
- returns: one graph with live state names only
- verify: count(subject="state graphs produced for one workflow class", equals=1)
- code: `workhorse/workhorse/pyflow/graph.py::state_graph`
- code: `workhorse/tests/test_pyflow_graph.py::test_both_arms_of_a_branch_become_edges`
- tests: `workhorse/tests/test_pyflow_graph.py::test_both_arms_of_a_branch_become_edges`, `workhorse/tests/test_pyflow_graph.py::test_an_alias_is_never_a_second_state`, `workhorse/tests/test_pyflow_graph.py::test_a_step_carries_the_docstring_line_or_the_prompt_title`

### registry_graphs
- sig: `registry_graphs(registry: Registry) -> list[FlowGraph]`
- does: groups registry flow names by distinct workflow class with the entry class first
- returns: one graph per distinct registered workflow class
- verify: count(subject="graphs produced for one registry with one flow class", equals=1)
- code: `workhorse/workhorse/pyflow/graph.py::registry_graphs`
- code: `workhorse/tests/test_pyflow_graph.py::test_registry_graphs_render_each_class_once_with_all_its_flow_names`
- tests: `workhorse/tests/test_pyflow_graph.py::test_registry_graphs_render_each_class_once_with_all_its_flow_names`

### preflight
- sig: `preflight(graphs: Sequence[FlowGraph], workflow_dir=None) -> list[str]`
- does: reports missing start states, terminal paths, opaque sources, dangling transitions, unreachable states, and missing prompts
- returns: problem strings, empty when static checks pass
- verify: count(subject="preflight problems for a valid workflow", equals=0)
- code: `workhorse/workhorse/pyflow/graph.py::preflight`
- code: `workhorse/tests/test_pyflow_graph.py::test_preflight_reports_an_unreachable_state`
- tests: `workhorse/tests/test_pyflow_graph.py::test_preflight_is_quiet_when_every_prompt_resolves`, `workhorse/tests/test_pyflow_graph.py::test_preflight_names_the_prompt_that_does_not_exist`, `workhorse/tests/test_pyflow_graph.py::test_preflight_reports_an_unreachable_state`, `workhorse/tests/test_pyflow_graph.py::test_preflight_reports_a_machine_that_cannot_terminate`, `workhorse/tests/test_pyflow_graph.py::test_preflight_reports_a_transition_to_something_that_is_not_a_state`

### StateNode.terminal
- sig: `terminal -> bool`
- returns: `true` when at least one recorded edge is a `done` edge
- verify: json_path(path="$.terminal", equals=true)
- code: `workhorse/workhorse/pyflow/graph.py::StateNode.terminal`
- code: `workhorse/tests/test_pyflow_graph.py::test_a_done_is_an_edge_out_of_the_state_beside_its_other_edge`
- tests: `workhorse/tests/test_pyflow_graph.py::test_a_done_is_an_edge_out_of_the_state_beside_its_other_edge`

### StateNode.handoffs
- sig: `handoffs -> tuple[str, ...]`
- returns: sub-workflow class names reached by handoff steps in source order
- verify: count(subject="handoffs reported by a state with one handoff", equals=1)
- code: `workhorse/workhorse/pyflow/graph.py::StateNode.handoffs`

### StateNode.calls
- sig: `calls -> tuple[str, ...]`
- returns: blueprint node names reached by call steps in source order
- verify: count(subject="node calls reported by a state with one call", equals=1)
- code: `workhorse/workhorse/pyflow/graph.py::StateNode.calls`
- code: `workhorse/tests/test_pyflow_graph.py::test_node_calls_and_prompt_paths_are_collected`
- detail: [Seam collector selection](seam-collector-selection.md)
- tests: `workhorse/tests/test_pyflow_graph.py::test_node_calls_and_prompt_paths_are_collected`, `workhorse/tests/test_pyflow_graph.py::test_a_seam_inside_a_private_helper_is_attributed_to_the_state`, `workhorse/tests/test_pyflow_graph.py::test_helpers_that_call_each_other_do_not_loop_the_reader`

### StateNode.prompts
- sig: `prompts -> tuple[str, ...]`
- returns: literal prompt paths passed to agent steps in source order
- verify: count(subject="prompt paths reported by a state with one agent step", equals=1)
- code: `workhorse/workhorse/pyflow/graph.py::StateNode.prompts`

## Fields

### field: Edge
- type: frozen dataclass
- required: true
- semantics: one statically discovered transition from a state
- verify: count(subject="transitions discovered from a state with one transition", equals=1)
- semantics: `target` is empty for a `done` edge
- verify: json_path(path="$.target", equals="")
- code: `workhorse/workhorse/pyflow/graph.py::Edge`
- detail: [Edge transition record](edge-transition-record.md)

### field: Step
- type: frozen dataclass
- required: true
- semantics: one source-ordered node call, agent turn, or sub-workflow handoff in a state
- code: `workhorse/workhorse/pyflow/graph.py::Step`
- detail: [Step field selection](step-field-selection.md)

### field: StateNode
- type: frozen dataclass
- required: true
- semantics: one live workflow state together with its discovered edges and source steps
- code: `workhorse/workhorse/pyflow/graph.py::StateNode`
- detail: [StateNode field selection](state-node-field-selection.md)

### field: FlowGraph
- type: frozen dataclass
- required: true
- semantics: one workflow class represented as a static machine graph
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph`
- detail: [FlowGraph fields](flow-graph-fields.md)

## Edge Fields

### field: Edge.target
- type: `str`
- default: empty string for a `done` edge
- required: true
- semantics: the statically named destination state
- code: `workhorse/workhorse/pyflow/graph.py::Edge`
- detail: [Edge transition record](edge-transition-record.md)

## StateNode Fields

### field: StateNode.name
- type: `str`
- required: true
- semantics: live workflow state name represented by the node
- code: `workhorse/workhorse/pyflow/graph.py::StateNode`
- detail: [StateNode field selection](state-node-field-selection.md)

### field: StateNode.edges
- type: `tuple[Edge, ...]`
- default: empty tuple
- required: true
- semantics: unique transitions discovered in the state's source
- code: `workhorse/workhorse/pyflow/graph.py::StateNode`
- detail: [StateNode field selection](state-node-field-selection.md)

### field: StateNode.steps
- type: `tuple[Step, ...]`
- default: empty tuple
- required: true
- semantics: unique engine seams discovered in source order
- code: `workhorse/workhorse/pyflow/graph.py::StateNode`
- detail: [StateNode field selection](state-node-field-selection.md)
- tests: `workhorse/tests/test_pyflow_graph.py::test_node_calls_and_prompt_paths_are_collected`, `workhorse/tests/test_pyflow_graph.py::test_a_seam_inside_a_private_helper_is_attributed_to_the_state`

### field: StateNode.opaque
- type: `bool`
- default: false
- required: true
- semantics: source inspection failed, so the state's transitions and steps are unknown
- code: `workhorse/workhorse/pyflow/graph.py::StateNode`
- detail: [StateNode field selection](state-node-field-selection.md)

## FlowGraph Fields

### field: FlowGraph.workflow
- type: `str`
- required: true
- semantics: workflow class name represented by the graph
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph`
- detail: [FlowGraph fields](flow-graph-fields.md)

### field: FlowGraph.names
- type: `tuple[str, ...]`
- default: empty tuple
- required: true
- semantics: registry flow names mapped to this workflow class
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph`
- detail: [FlowGraph fields](flow-graph-fields.md)

### field: FlowGraph.start
- type: `str`
- default: empty string
- required: true
- semantics: state name from which reachability is explored
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph`
- detail: [FlowGraph fields](flow-graph-fields.md)

### field: FlowGraph.states
- type: `tuple[StateNode, ...]`
- default: empty tuple
- required: true
- semantics: statically read live states in stable name order
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph`
- detail: [FlowGraph fields](flow-graph-fields.md)

### field: Edge.kind
- type: `str`
- default: `continue`
- required: true
- semantics: `continue`, `await`, or `done`
- code: `workhorse/workhorse/pyflow/graph.py::Edge`
- detail: [Edge transition record](edge-transition-record.md)
- code: `workhorse/tests/test_pyflow_graph.py::test_an_await_edge_is_read_from_the_third_argument`
- tests: `workhorse/tests/test_pyflow_graph.py::test_a_done_is_an_edge_out_of_the_state_beside_its_other_edge`, `workhorse/tests/test_pyflow_graph.py::test_an_await_edge_is_read_from_the_third_argument`

### field: Edge.params
- type: `tuple[str, ...]`
- default: empty tuple
- required: true
- semantics: names of parameters bound on the destination state
- code: `workhorse/workhorse/pyflow/graph.py::Edge`
- detail: [Edge transition record](edge-transition-record.md)
- code: `workhorse/tests/test_pyflow_graph.py::test_edge_labels_name_the_parameters_the_transition_binds`
- tests: `workhorse/tests/test_pyflow_graph.py::test_edge_labels_name_the_parameters_the_transition_binds`

### field: Edge.reason
- type: `str`
- default: empty string
- required: true
- semantics: literal reason supplied to `.because()`, or empty when it is not statically knowable
- code: `workhorse/workhorse/pyflow/graph.py::Edge`
- detail: [Edge transition record](edge-transition-record.md)
- code: `workhorse/tests/test_pyflow_graph.py::test_a_chained_because_is_read_as_the_edge_reason`
- tests: `workhorse/tests/test_pyflow_graph.py::test_a_chained_because_is_read_as_the_edge_reason`

### field: Edge.dynamic
- type: `bool`
- default: false
- required: true
- semantics: the target expression was not a plain `self.<state>` reference
- code: `workhorse/workhorse/pyflow/graph.py::Edge`
- detail: [Edge transition record](edge-transition-record.md)
- code: `workhorse/tests/test_pyflow_graph.py::test_a_target_the_source_cannot_name_is_reported_as_dynamic`
- tests: `workhorse/tests/test_pyflow_graph.py::test_a_target_the_source_cannot_name_is_reported_as_dynamic`

### field: Edge.dangling
- type: `bool`
- default: false
- required: true
- semantics: a plain target names no live state
- code: `workhorse/workhorse/pyflow/graph.py::Edge`
- detail: [Edge transition record](edge-transition-record.md)
- code: `workhorse/tests/test_pyflow_graph.py::test_preflight_reports_a_transition_to_something_that_is_not_a_state`
- tests: `workhorse/tests/test_pyflow_graph.py::test_preflight_reports_a_transition_to_something_that_is_not_a_state`

## Fields of Step

### field: Step.kind
- type: `str`
- required: true
- semantics: `call`, `agent`, or `handoff`
- code: `workhorse/workhorse/pyflow/graph.py::Step`
- detail: [Step field selection](step-field-selection.md)

### field: Step.name
- type: `str`
- required: true
- semantics: node name, literal prompt path, or child workflow class name according to `kind`
- code: `workhorse/workhorse/pyflow/graph.py::Step`
- detail: [Step field selection](step-field-selection.md)

### field: Step.summary
- type: `str`
- default: empty string
- required: true
- semantics: first line of a node docstring or prompt title when available
- code: `workhorse/workhorse/pyflow/graph.py::Step`
- detail: [Step field selection](step-field-selection.md)
- code: `workhorse/tests/test_pyflow_graph.py::test_a_step_carries_the_docstring_line_or_the_prompt_title`
- tests: `workhorse/tests/test_pyflow_graph.py::test_a_step_carries_the_docstring_line_or_the_prompt_title`

### method: Step.file
- code: `workhorse/workhorse/pyflow/graph.py::Step.file`
- sig: `file -> str`
- returns: the final path component of the step name
- verify: json_path(path="$.file", equals="review.md")

## Contract

`state_graph(cls, names=())` accepts a `Workflow` subclass and the flow names a
[`Registry`](pyflow-driver.md) maps to it.

- consistency: flow-graph — `registry_graphs(registry)` returns one `FlowGraph` per distinct workflow class,
  with the entry flow first and all of the class's registered names collected on that graph.
- verify: count(subject="FlowGraph entries for one workflow class registered under multiple names", equals=1)
- **Output:** a `FlowGraph` — `workflow` (the class name), `names`, `start`, and one `StateNode`
  per **live** state name. Aliases never appear: the walk is over `cls.state_names()`, so a
  renamed state shows one node, not two.
- **Raises:** nothing. A state whose source cannot be read (`inspect.getsource` on a REPL- or
  `exec`-defined method) is marked `opaque` and reported by `preflight` as a hole in the
  analysis, rather than failing the render.

### `StateNode`

| Field | Meaning |
|---|---|
| `edges` | one `Edge` per transition constructed in the body, `Done` included |
| `steps` | what the body runs, in source order: one `Step(kind, name, summary)` per `self.call` (`kind="call"`, summary = the node docstring's first line), `self.agent` (`"agent"`, summary = the prompt's `#` title with a leading `<workflow> — ` trimmed) or `self.handoff` (`"handoff"`, the sub-workflow's class name) |
| `terminal` | derived: some edge is a `done` edge — the machine can end here |
| `calls` / `prompts` / `handoffs` | derived from `steps` by kind; a prompt is a **literal** path, an f-string prompt is unknowable statically and is skipped rather than guessed |
| `opaque` | the source could not be read; nothing below it is known |

### `Edge`

`target`, `kind` (`continue` | `await` | `done`), the `params` the transition binds, the `reason` a
chained `.because("…")` gave (the edge label when set; a non-literal reason reads as `""`),
and two error flags: `dynamic` (the target was not a plain `self.<state>` — the edge is real, but
where it goes is only known at runtime) and `dangling` (a `self.<name>` that is not a state).

## Algorithm

1. **Read each state.** `textwrap.dedent(inspect.getsource(fn))` → `ast.parse` → `ast.walk` over
   every `ast.Call`. `ast.walk` rather than a visitor, so a transition constructed inside a
   nested helper or a comprehension still counts — over-reporting is the contract anyway.
2. **Read the target off its positional slot.** `Continue(result, next, /, …)` keeps it at index
   1 and `Await(path, questions, next, /, …)` at index 2; both are positional-only, so a keyword
   can never carry the target. A target that is not `self.<attr>` yields a `dynamic` edge labeled
   with `ast.unparse` of the expression.
3. **Label the edge.** Keywords are read from the callsite; extra positional arguments carry no
   name there, so they are resolved against the *target's own signature* — the same binding the
   driver does at runtime, done here only to label an edge.
4. **Reachability.** BFS from `start` over statically readable edges. A `dynamic` or `dangling`
   edge is a **dead end** on purpose: it is precisely the case where the target is unknown, so
   counting it as reaching everything would make the unreachable check useless, and counting it
   as reaching nothing is the honest over-report the caller is told about.

## `preflight`

Everything a static read can see, as a list of `flow '<label>': …` strings — empty means clean.
It is the half of `--dry-run` that no run can do, because it sees the branches this run would
never take:

- the `start` state does not exist
- no state returns `Done(...)` — the machine cannot terminate
- a state's source could not be read (`opaque`)
- a state transitions to `self.<name>`, which is not a state
- a state is unreachable from `start`
- a state renders a prompt path that does not exist (resolved the way
  [`render`](render-prompt.md) resolves it: relative to the workflow directory, absolute
  taken as-is)

Argument *types* are not checked here — `ParamSpec` and the editor cover those long before a run
starts. What is left is the filesystem and the graph, which is what this is.

## Rendering

`pyflow/dot.py::to_dot` emits one `subgraph cluster_*` per flow, so a distribution shipping
several flows renders as one document; node ids are flow-prefixed (`f0__start`) so two flows
sharing a state name never collide in DOT's single namespace, while the visible label stays the
bare name. A state is a rounded box holding one bubble per `Step`, transitions clipped to the box's
border (`compound=true`, `newrank=true`), so the reader follows the machine between boxes
and the work inside them on one page:

| Shape | Meaning |
|---|---|
| lightgreen circle | `START`, one per flow |
| gold double circle | `END`, one per flow; every `done` edge points at it |
| rounded lightblue box | a state; empty when it runs nothing |
| white box in a state | a node call, captioned with its docstring's first line |
| lightyellow note in a state | an agent turn, captioned with the prompt's title |
| plum box in a state | a handoff, captioned `handoff → <flow label>`; never a cross-flow edge |
| lightcoral | unreachable, opaque, or a dangling target (`<name>?`) |
| `shape=note`, lightgray | a dynamic target, drawn as its own sink rather than as a state |
| dashed darkorange edge | an `Await` — the transition waits for a human first |
| darkgoldenrod edge | a `Done` |

An edge is labelled with its `reason` when the author wrote one, else with the parameter
names it binds. A state is never drawn terminal: `Done` on one branch does not stop the
other, so the ending is the edge into `END`. A legend cluster draws the vocabulary once.

- code: `workhorse/tests/test_pyflow_graph.py::test_dot_prefers_the_reason_over_parameter_names`
- tests: `workhorse/tests/test_pyflow_graph.py::test_dot_prefers_the_reason_over_parameter_names`, `workhorse/tests/test_pyflow_graph.py::test_dot_renders_one_cluster_per_flow_with_live_names_only`, `workhorse/tests/test_pyflow_graph.py::test_dot_draws_a_state_as_the_chain_of_steps_it_runs`, `workhorse/tests/test_pyflow_graph.py::test_dot_marks_an_await_edge_and_labels_bound_parameters`, `workhorse/tests/test_pyflow_graph.py::test_dot_draws_done_as_an_edge_to_one_end_sink_per_flow`, `workhorse/tests/test_pyflow_graph.py::test_dot_draws_a_handoff_as_a_coloured_bubble_and_never_an_edge`, `workhorse/tests/test_pyflow_graph.py::test_dot_ids_are_flow_prefixed_so_two_flows_may_share_a_state_name`

- tests: `workhorse/tests/test_pyflow_graph.py::test_dot_prefers_the_reason_over_parameter_names`, `workhorse/tests/test_pyflow_graph.py::test_dot_renders_one_cluster_per_flow_with_live_names_only`, `workhorse/tests/test_pyflow_graph.py::test_dot_draws_a_state_as_the_chain_of_steps_it_runs`, `workhorse/tests/test_pyflow_graph.py::test_dot_marks_an_await_edge_and_labels_bound_parameters`, `workhorse/tests/test_pyflow_graph.py::test_dot_draws_done_as_an_edge_to_one_end_sink_per_flow`, `workhorse/tests/test_pyflow_graph.py::test_dot_draws_a_handoff_as_a_coloured_bubble_and_never_an_edge`, `workhorse/tests/test_pyflow_graph.py::test_dot_ids_are_flow_prefixed_so_two_flows_may_share_a_state_name`
