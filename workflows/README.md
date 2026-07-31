# workhorse-workflows

The stablemate agent workflows as an installable Python distribution: `research`,
`author`, `okf-builder` and `coder`, each a checkpointed state machine. Workhorse is the
engine; this is its content.

**Not on PyPI yet** — install it from a checkout of the
[stablemate](https://github.com/GabrielCpp/stablemate) workspace, into the *same*
interpreter as workhorse, because a workflow runs in workhorse's own process:

```bash
make sync                              # at the workspace root: engine + workflows, one venv
uv run workhorse run research          # resolved through the entry-point group
uv run workhorse-research run          # the same parser, name already bound
```

The shape came from the
[workflow-as-python-state-machine](../docs/plans/workflow-as-python-state-machine.md)
design brief, which shipped and is now kept only for its reasoning. What is still
outstanding *here* is noted under [Status](#status).

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
  kit/            shared workflow-side helpers (git.py, github.py, workspace.py)
  <workflow>/
    workflow.py   the Workflow subclass and `main` — one class, nothing else
    schemas.py    agent-reply schemas and node return types  (→ schemas/ when it grows,
                  as it has in author/ and coder/)
    paths.py      pure derivations: the dirs and filenames the nodes agree on
    nodes/        the callables, one module per subject, assembled into a Blueprint
                  by nodes/__init__.py
    flows/        sub-workflows, each its own Workflow subclass reached by handoff()
    prompts/      the agent-facing markdown, rendered by a filesystem template loader

tests/<workflow>/  outside src/ and outside the wheel; mirrors the node modules,
                   plus one test_workflow.py for the machine
```

A workflow may add modules of its own beside those — `coder/` carries `contract.py`,
`ostler_qa.py` and `story_status.py`, and `research/` a `scaffold/` package — but the
six names above mean the same thing in every one.

Imports point one way: `workflow.py` imports `nodes/`, `flows/`, `schemas` and `paths`;
nothing under `nodes/` imports `workflow.py`.

How small each of those files has to be is **normative, not per-workflow taste** — one
subject per module, `nodes/` is a package even when it holds three functions, and
`~400 lines` is the trigger to apply the rule. This README is where that rule is stated;
the argument behind it is "One workflow, several files" in the
[retired design brief](../docs/plans/workflow-as-python-state-machine.md).
`coder`'s nodes alone run to ~6,600 lines across 18
modules, and a single `nodes.py` at that size is `scriptutil.py` again.

## Status

All four workflows are ported and resolve through the entry-point group; the YAML engine
they came from is retired, so this package is the only place a stablemate workflow lives.

What is still outstanding: this distribution is unpublished, so there is no `pip install`
route to it and a `pipx` layout needs `pipx inject workhorse-agent <this distribution>`
to land it in the engine's venv. Farrier also still validates a `workflows:` selection
against a `workflows/<name>/` directory in a library layer rather than against the entry
points — see the end of
[farrier/docs/LAYOUT.md](../farrier/docs/LAYOUT.md).
