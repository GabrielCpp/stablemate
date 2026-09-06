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

### FlowGraph.reachable
- sig: `reachable() -> set[str]`
- returns: states reachable from the start over non-dynamic, non-dangling edges
- verify: count(subject="reachable states in a two-state flow", equals=2)
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph.reachable`

### FlowGraph.unreachable
- sig: `unreachable() -> tuple[str, ...]`
- returns: live states not reached by the static walk
- verify: count(subject="unreachable states in a connected flow", equals=0)
- code: `workhorse/workhorse/pyflow/graph.py::FlowGraph.unreachable`

### state_graph
- sig: `state_graph(cls: type[Workflow], names=(), workflow_dir=None) -> FlowGraph`
- does: parses every live state source and records transitions and engine seams in source order
- returns: one graph with live state names only
- verify: count(subject="state graphs produced for one workflow class", equals=1)
- code: `workhorse/workhorse/pyflow/graph.py::state_graph`

### registry_graphs
- sig: `registry_graphs(registry: Registry) -> list[FlowGraph]`
- does: groups registry flow names by distinct workflow class with the entry class first
- returns: one graph per distinct registered workflow class
- verify: count(subject="graphs produced for one registry with one flow class", equals=1)
- code: `workhorse/workhorse/pyflow/graph.py::registry_graphs`

### preflight
- sig: `preflight(graphs: Sequence[FlowGraph], workflow_dir=None) -> list[str]`
- does: reports missing start states, terminal paths, opaque sources, dangling transitions, unreachable states, and missing prompts
- returns: problem strings, empty when static checks pass
- verify: count(subject="preflight problems for a valid workflow", equals=0)
- code: `workhorse/workhorse/pyflow/graph.py::preflight`

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
