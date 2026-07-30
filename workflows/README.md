# workhorse-workflows

The stablemate agent workflows as an installable Python distribution — the shape the
[workflow-as-python-state-machine](../docs/plans/workflow-as-python-state-machine.md)
plan moves them into. Workhorse is the engine; this is its content.

```bash
uv pip install workhorse-workflows
workhorse run research                 # resolved through the entry-point group
workhorse-research run                 # the same parser, name already bound
```

## How workhorse finds a workflow in here

A distribution advertises what it ships:

```toml
[project.entry-points."workhorse.workflows"]
research = "workhorse_workflows.research.workflow:workflow"

[project.scripts]
workhorse-research = "workhorse_workflows.research.workflow:main"
```

The **entry point** points at the `Workflow` object, because discovery needs the
registry rather than the entry function. The **console script** points at `main` — the
callable `workflow.main(Entry)` *returns*, since a script target is called after
import, not during it.

`workhorse run <name>` resolves the entry point and hands the name to the same parser
`workhorse-<name>` uses. There is one parser on purpose: two commands with two parsers
is the failure this shape invites.

Nothing here is a plugin API for workhorse. A third party can register the same group
— that is what makes the mechanism plural — but the engine still knows no workflow's
vocabulary, and this package still imports the engine and never the other way.

## Installed unpacked, always

Workhorse renders a workflow's prompts with a filesystem template loader rooted at the
workflow's own package directory, and keys per-node overrides on that directory's
name. A wheel installed by pip or uv satisfies this; a zipapp or zip-safe egg does
not, and workhorse refuses one at resolution rather than failing later as a missing
template.

## Layout

```
src/workhorse_workflows/
  kit/            shared workflow-side helpers (GitHub, git, workspace resolution)
  <workflow>/
    workflow.py   the Workflow subclass and `main` — one class, nothing else
    schemas.py    agent-reply schemas and node return types  (→ schemas/ when it grows)
    paths.py      pure derivations: the dirs and filenames the nodes agree on
    nodes/        the callables (today's scripts/), one module per subject,
                  assembled into a Blueprint by nodes/__init__.py
    flows/        sub-workflows, each its own Workflow subclass reached by handoff()
    prompts/      unchanged from the YAML era

tests/<workflow>/  outside src/ and outside the wheel; mirrors the node modules,
                   plus one test_workflow.py for the machine
```

Imports point one way: `workflow.py` imports `nodes/`, `flows/`, `schemas` and `paths`;
nothing under `nodes/` imports `workflow.py`.

How small each of those files has to be is **normative, not per-workflow taste** — one
subject per module, `nodes/` is a package even when it holds three functions, and
`~400 lines` is the trigger to apply the rule. The plan's
[One workflow, several files](../docs/plans/workflow-as-python-state-machine.md) carries
the rules and the reasoning; `coder` is 71 scripts totalling 8,661 lines, and a single
`nodes.py` at that size is `scriptutil.py` again.

## Status

`research` has landed — the first port, and the one the driver is proved against.
`author`, `okf-builder` and `coder` follow, one at a time, and the YAML engine keeps
running the un-ported ones from the base library the whole way.
