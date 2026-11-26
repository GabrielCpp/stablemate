# Where a flow lives

Reached from [../SKILL.md](../SKILL.md) when you add a workflow, or move a flow between the engine and a distribution.

**One directory per machine.** A workflow is a graph plus the sub-graphs it hands off to,
and each of those is a state machine with nodes of its own. The **entry machine lives in
`main/`**, laid out exactly like any other flow — not at the package root.

```
workflows/src/workhorse_workflows/<name>/
├── workflow.py          # the composition root, and nothing else: the Registry, the flow
│                        #   table, the console script. No state, no node, no schema.
├── main/                # the machine a bare `workhorse-<name> run` starts
│   ├── flow.py          #   its Workflow subclass — the entry class workflow.py names
│   ├── nodes/           #   the callables only main calls
│   └── prompts/         #   the markdown only main renders
├── <flow>/              # one directory per sub-graph, named for the flow
│   ├── flow.py          #   its Workflow subclass, reached by handoff() or run directly
│   ├── nodes.py         #   the callables only this flow calls (→ nodes/ once it grows)
│   └── prompts/
└── shared/              # what a second machine also reaches
    ├── blueprint.py     #   `blueprint = Blueprint("<name>")` — the one every node decorates
    ├── paths.py         #   the only caller of `ostler.path`: doc dirs and filenames
    ├── schemas/         #   the models states and nodes exchange, with their @dry_run replies
    ├── stubs.py         #   the nodes' --dry-run stand-ins
    └── <subject>.py     #   a node module more than one machine calls
```

`workflow.py` composes and stops there:

```python
workflow = (
    Registry("acme", package=__package__)
    .add_blueprints(blueprint)
    .add_flows(dev=Dev, qa=Qa)
)
main = console_script(workflow.entry_point(Acme))   # Acme comes from acme.main.flow
```

The distribution binds each workflow to a command in `[project.scripts]`
(`workhorse-<name> = "…workflow:main"`), and that command carries the registry itself.
Nothing is resolved by name and nothing is found by file path.

**What goes in `shared/` is a count, not a judgement.** Every module belongs to the machine
that calls it; a module a *second* machine also calls moves to `shared/`, and the move is
mechanical enough to check by grep. A shared node module keeps the name of its **subject**,
not of the flow that reads it most.

**Prompt paths are written from the package root down**, because `Registry(name,
package=__package__)` makes the package directory the template root:

```python
self.agent("main/prompts/settle-worktree.md", …)      # from a main/ state
self.agent("dev/prompts/implement-plan.md", …)        # from the dev sub-flow
self.agent("shared/prompts/resolve-operator.md", …)   # a turn both machines render
```

`handoff` subscopes the run *writer*, not the template root, so a sub-flow's prompt still
resolves against the parent package. Were the root inferred from the entry class instead,
moving that class into `main/` would put every sibling flow's prompts outside it. A prompt
two flows both render is **two files**, one per flow, each free to diverge.

**A workflow with one machine has no `main/` and no `shared/`** — `workflow.py` + `nodes/`
+ `prompts/` at the package root, and nothing more. There is nothing to share and nothing
to disambiguate until a second machine exists.

**The blueprint sits where the nodes that decorate it can import it without a cycle.** One
`shared/blueprint.py` for the whole distribution is the default. A flow that ships its own
puts it in `<flow>/nodes/_blueprint.py` and `workflow.py` passes it to `add_blueprints`
alongside the rest.

**Imports point one way.** `workflow.py` imports `main/`, each `<flow>/` and `shared/`; a
`<flow>/` imports its own nodes and `shared/`; nothing under either imports `workflow.py`,
and nothing in `shared/` imports a flow.

One subject per module is normative, not per-workflow taste. `nodes/` is a package even
when it holds three functions, and ~400 lines is the trigger to split.
