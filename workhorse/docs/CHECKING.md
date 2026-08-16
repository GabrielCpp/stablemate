# Reading a workflow without running it — `--dry-run` and `dot`

Two commands answer questions about a workflow from its own source, so neither can drift
from it: `--dry-run` turns "is this workflow sound?" into an exit code, and `dot` renders
the state machine to Graphviz. This document is both in full — what the static pass checks,
what the substituted node index covers, what a fail terminal means with and without declared
stand-ins, and how the graph is read off the states. See [README.md](../README.md) for
running a workflow for real.

## `--dry-run`: checking a workflow before you run it

`--dry-run` checks a workflow and exits without running a node — `0` when it is
clean, `1` on the first problem, so CI can read it. The failure it exists to catch
is a typo found at hour 30 of an unattended run.

```bash
workhorse-coder run --dry-run
```

It turns the skill/prompt reference warning a normal launch prints (see
[Running a workflow](../README.md#running-a-workflow-workhorse-name-run)) into an exit
code, and then does two complementary things.
First a **static pass** over the states' own source (the same reading `dot` uses):
every prompt path a state renders must exist, every state must be reachable from the
start state, at least one state must be able to return `Done`, and no transition may
name something that is not a state. Then it **drives the machine for real** over a
*substituted node index*, which covers what only running can — imports, `setup()`, and
the transitions actually bound along one path. The static half is the one that carries
the weight: it sees the branches this run would never take.

Nothing branches on "is this a dry run" inside the driver. The run is handed a copy of
the registry's node index with every node's body replaced by its stand-in, so `self.call`
runs the same code path it always does — see
[The node index is the substitution seam](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#the-node-index-is-the-substitution-seam).
A node's stand-in is whatever `@blueprint.node(stub=…)` declared, or a blank instance of
its declared return type; an agent turn's is whatever `Registry.stub_agents({...})`
declared for that prompt stem, or a blank reply model.

**What a fail terminal means depends on whether the workflow declared any stand-ins.**
Undeclared, every reply is blank, so the machine takes whichever branch a blank selects
— and for any workflow with a reachable `raise WorkflowFailed` that can be the failing
one, which would mean no such workflow could ever dry-run green. So a dry run prints
which state halted and why, marks the run dir `fail`, and still exits `0`. A workflow
that calls `stub_agents({...})` has *said* what the happy path answers, so reaching a
fail terminal anyway is a real finding and exits `1`. Every other deliberate failure (a
dead state, a bad checkpoint parameter, an exhausted transition budget) exits `1` either
way.

A dry run writes its artifacts to a run dir named `dry-run` and clears it first, so
it can never resume — or overwrite — the checkpoint of a real week-long run. Each seam
it entered is marked in `events.jsonl` with which stand-in answered it —
`"stub": "declared"` for one the workflow supplied, `"blank"` for the default empty
model — which is how you tell a path the workflow *meant* from one a blank reply picked.

## `dot`: diagramming a workflow (`workhorse-<name> dot`)

`dot` renders a workflow to [Graphviz](https://graphviz.org) DOT straight
from the workflow, so the diagram never drifts from it.

```bash
workhorse-coder dot                         # DOT to stdout
workhorse-coder dot -o wf.dot               # ...to a file
dot -Tsvg wf.dot -o wf.svg                  # render (needs graphviz)
```

A workflow is rendered from its states: one cluster per flow, a `box3d` green node for every state that can return
`Done`, dashed orange edges for an `Await`, coral for a state nothing reaches, and
edge labels naming the parameters each transition binds. The graph is read off the
states' source, so both arms of an `if` appear (it over-approximates) and it cannot
drift from the code. A state that factors a repeated turn into a private helper keeps
its annotations: `self._helper(...)` is followed into the class's own underscore
methods, and what it finds is attributed to the state that called it — the helper is
not a node. Aliases are never drawn as a second state.

| Flag | Purpose |
|---|---|
| `--name <id>` | Override the `digraph` identifier (default: sanitized workflow name) |
| `-o, --output <path>` | Write to a file instead of stdout |

There is no flag for carving one mode out of a multi-mode workflow: a state machine's
branches are ordinary Python, so there is no declared branch variable to pin. Give the
mode its own flow if its diagram should stand alone.
