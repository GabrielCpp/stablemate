---
type: flow
slug: workhorse-author-visualize-run
title: Author, visualize, and run a workflow
---
# Author, visualize, and run a workflow

The design-time path from an empty package to a live run: write the state machine per the
[workflow format](../workflow-format.md), read its shape back with
[`workhorse dot`](../workhorse.md#dot), rehearse it with
[`workhorse run <name> --dry-run`](../workhorse.md#run), and only then commit to a real,
unattended [`workhorse run`](../workhorse.md#run). The two checks are deliberately different
tools: `dot` and `--dry-run`'s preflight read **every** path off the source, while the
rehearsal walks **one** — the path a machine of stand-in values happens to take.

- start: a Python package that is installed (`pip install -e .`) and publishes a name in the
  `workhorse.workflows` entry-point group, but has never been executed.
- steps:
  1. **Author the machine** — a [`Registry`](../workflow-format.md#registry) under the
     workflow's name, one or more [`Workflow`](../workflow-format.md#workflow-subclass)
     subclasses whose methods are its [states](../workflow-format.md#state), the
     [`@blueprint.node`](../workflow-format.md#node) functions those states call, and the
     `prompts/` each [agent turn](../workflow-format.md#the-agent-turn) renders. Nothing
     declares the graph: an edge *is* a
     [`Continue`/`Await`](../workflow-format.md#transition) a state returns, so there is no
     separate document to keep in sync and nothing to validate before the package imports.
  2. **Read the shape back** with [`workhorse dot <name>`](../workhorse.md#dot) — the same
     name resolution `run` uses, then
     [`state_graph`](../concepts/pyflow-state-graph.md) parses each state's own source and
     [`to_dot`](../concepts/pyflow-state-graph.md#rendering) emits Graphviz DOT to stdout (or
     `--output <file>`, with `--name` overriding the digraph identifier). One
     `subgraph cluster_*` per flow; a state's label lists what it runs (`call …`, `agent …`,
     `handoff …`). Because it is a static read it **over-approximates** — both arms of an
     `if` are drawn — and it cannot drift from the code the way a hand-maintained edge list
     can. A dangling target, an unreachable state, or a dynamic target that is only known at
     runtime is visible in the diagram (`<name>?`, lightcoral, `shape=note`) before anything
     has run.
  3. **Rehearse it** with [`workhorse run <name> --dry-run`](../workhorse.md#run) — first
     [`preflight`](../concepts/pyflow-state-graph.md#preflight) reports everything a static
     read can see (a missing `start`, a machine that can never return `Done`, a state whose
     source cannot be read, a transition to a name that is not a state, an unreachable
     state, a prompt path that does not exist) and **errors out** rather than warning; then
     the driver walks the machine over a substituted node index — declared
     `@blueprint.node(stub=…)` bodies and `Registry.stub_agents({stem: reply})` replies — so
     no node body runs and no agent CLI is launched. A workflow that declares no agent
     stand-ins gets a blank reply for every turn, so reaching a fail terminal there is
     reported and still exits `0`; one that *has* said what the happy path answers exits `1`
     when it fails anyway.
  4. **Iterate.** Steps 1–3 repeat until both reads match intent. Neither costs an agent
     turn.
  5. **Run it for real** with [`workhorse run <name> [<flow>]`](../workhorse.md#run) —
     the same resolution, the same driver, the real node bodies and the `--cli`
     [agent backend](../concepts/agent-backend.md), checkpointing `(state, params)` before
     every transition.
- end: the process exits `0` (the entry flow returned `Done`) or `1` (a `PyflowError`, or a
  dry run whose declared stand-ins still walked into a failure). On a genuine run the
  [run artifacts](../run-artifacts.md) under `<runs_dir>/<name>-<run_id>` record the outcome
  and make it resumable, continuing the [crash-and-resume](workhorse-crash-resume.md)
  journey if it dies mid-machine.
- verify: `workhorse/tests/test_pyflow_graph.py::test_dot_renders_a_python_workflow_from_its_registry`,
  `workhorse/tests/test_pyflow.py::test_dry_run_records_the_calls_without_making_them`,
  `workhorse/tests/test_pyflow.py::test_a_dry_run_answers_a_prompt_with_the_reply_the_registry_declared`
