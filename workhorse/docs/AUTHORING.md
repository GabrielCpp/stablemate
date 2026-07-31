# Writing a workflow

This is the authoring reference for workhorse workflows: the package layout, the three
tiers of state, transitions, checkpoints and aliases, the node index that tests substitute
through instead of patching, and the labels that tell a collector what a run is doing.

It assumes you can already run a workflow. If you cannot yet, run the shipped quick start
first — it needs no repository and, under `--dry-run`, no agent CLI at all:

```bash
workhorse run hello-world --dry-run
```

Its whole source is one ~60-line file,
[`workflows/src/workhorse_workflows/hello_world/workflow.py`](https://github.com/GabrielCpp/stablemate/blob/main/workflows/src/workhorse_workflows/hello_world/workflow.py),
carrying one of each thing this document describes: a node, two states, an agent turn and
a registry. **Copy that file** and edit it — every example below is a variation on it.
[README.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/README.md) covers
install, the CLI and `--dry-run` in full. The resilience knobs the failure paths below land in are
in
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md),
and the `power=` tiers a turn asks for are mapped to models in
[docs/BACKENDS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/BACKENDS.md).

> Holding a `workflow.yaml` from the retired YAML engine? `docs/WORKFLOW.md` maps every
> construct in that schema to what replaces it here, and
> [Why a workflow is Python and not a config file](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/README.md#why-a-workflow-is-python-and-not-a-config-file)
> is why that schema is gone.

A workflow is a Python package with this layout:

```
my_workflow/
├── workflow.py         # The Registry, the Workflow classes, the console script
├── nodes.py            # @blueprint.node functions
└── prompts/            # Jinja2 .md templates
    └── step.md
```

Its **states** are methods on a `Workflow` subclass, each returning the next state;
its **nodes** are plain functions collected into a `Blueprint`; a `Registry` names the
whole thing and is what the `workhorse.workflows` entry point resolves to. Control flow
is ordinary Python — `if`, `for`, a counter that is just a counter.

## Shipping your own, outside this repo

`workhorse run <name>` resolves a name **only** through the `workhorse.workflows`
entry-point group — there is no path form and no directory it scans. So a workflow of your
own is a distribution, and this is the whole of it:

```toml
# acme-workflows/pyproject.toml
[project]
name = "acme-workflows"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["workhorse-agent"]

[project.entry-points."workhorse.workflows"]
greeter = "acme_workflows.greeter.workflow:workflow"   # the Registry OBJECT, not main

[project.scripts]
workhorse-greeter = "acme_workflows.greeter.workflow:main"   # optional second front door

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/acme_workflows"]
```

Two details are load-bearing rather than taste:

- **The entry point names the `Registry`, not the entry function.** Discovery needs the
  registry object — `main` is the console script, and pointing the entry point at it fails
  at resolution rather than at run time.
- **It must install unpacked.** Prompts are rendered by a filesystem template loader rooted
  at the package directory, so a zip-imported install is refused. Nothing special is needed
  for this — it is what wheels do by default — but do not set `zip-safe`-style options.

Then install it **into workhorse's own interpreter**, because a workflow's code and its
tools are imported in-process:

```bash
uv pip install ./acme-workflows       # or: pipx inject workhorse-agent ./acme-workflows
uv run workhorse run greeter --dry-run
```

Copying `hello_world/` and changing the two `Registry("hello-world")` / entry-point names
is the shortest route to a green run of your own; everything below is what you add next.

**Agent prompts** must output JSON matching the model the turn declared in `returns=`:

````markdown
Do the thing.

Output JSON only:

```json
{"status": "ok", "count": 5}
```
````

## Unattended resilience (defaulted outputs)

Because runs are meant to survive a week without supervision, the runner will, as a
last resort, **emit an agent turn's declared output keys as nulls and let the state
carry on** rather than crash when the model can't be coaxed into a usable answer (after
transient retries and prompt reframing — see [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md)).

The keys come from the `returns=` model, so a state must be ready for a reply whose
fields are empty: give the branch it drives a safe arm, the way a long-running machine
needs a route that keeps moving. To disable defaulting entirely and hard-fail instead,
set `AGENT_USE_DEFAULT_OUTPUTS=false`.

## A worked example

Illustrative, and deliberately a step past the quick start: it adds `setup()`, a loop and
a second state. The runnable counterpart is `hello-world` above — reach for that one when
you want something you can execute rather than read.

```python
from workhorse.cli import console_script
from workhorse.pyflow import Blueprint, Continue, Done, Registry, Workflow

blueprint = Blueprint("acme")


@blueprint.node
def measure(logger, subject: str) -> Reading:      # a node is a plain function
    return Reading(kind=subject, count=len(subject))


class Build(Workflow):
    subject: str                                   # inputs — filled from --params

    def setup(self) -> Settings:                   # runs once; its return becomes self.ctx
        return Settings.load(self.subject)

    def start(self):
        reading = self.call(measure, self.subject)
        return Continue(None, self.review, count=reading.count)

    def review(self, count: int):                  # state parameters — one hop only
        verdict = self.agent("prompts/review.md", returns=Verdict, args={"n": count})
        if verdict.ok:
            return Done(verdict)
        return Continue(None, self.review, count=count + 1)


workflow = Registry("acme").add_blueprints(blueprint)
main = console_script(workflow.entry_point(Build))  # the `workhorse-<name>` console script
```

## The three tiers of state, and no fourth

| Tier | Written by | Lives for | Reached as |
|---|---|---|---|
| Inputs | the CLI (`--params`) | the whole run | `self.<field>` |
| `self.ctx` | `setup()`, once | the whole run | `self.ctx` |
| State parameters | the previous state | one hop | the state's own arguments |

The rule that keeps a run resumable: **if a state writes it, it is a parameter of the
next state.** Nothing else is carried, and the instance *freezes* once `setup()` returns
— assigning to `self.subject` from inside a state raises rather than producing a value
that survives in memory but not in the checkpoint.

`self.output(node)` is a read, not a fourth tier: it re-reads the node's recorded
`output.json` (the latest invocation, validated back into the node's declared return
type) and raises when the node has not run.

## Where an agent turn runs (`cwd` / `add_dirs`)

`self.agent` takes four optional keywords beyond the prompt, all defaulting to "whatever
the engine defaults to", so a state that says nothing behaves as before:

```python
review = self.agent(
    "prompts/review.md",
    returns=Verdict,
    args={"unit": unit_id},
    power="medium",                       # the abstract tier the config maps to a model
    timeout=1800,                         # this turn's wall-clock budget, seconds
    cwd=self.ctx.repo_root,               # where the CLI is launched
    add_dirs=[self.ctx.docs_root],        # further directories it may read
)
```

`cwd` matters more than it looks: it decides whose `CLAUDE.md`, skills and git context the
turn sees. The runner de-dupes `add_dirs` against it and turns the rest into `--add-dir`
flags.

These are **real values, not templates**: the state computes the path in Python and
passes it. (They are still Jinja-rendered on the way through, so a literal path is a
no-op render and a template string would also work — but nothing needs one.)

## Transitions

A state returns one of three things, or raises:

| Return | Meaning |
|---|---|
| `Continue(result, self.next_state, **params)` | go to `next_state` with those parameters |
| `Done(result)` | the flow is finished; `result` is what a `handoff` caller receives |
| `Await(path, questions, self.next_state, **params)` | write `questions` to `path`, checkpoint, and wait for a human to touch the file |
| `raise WorkflowFailed(reason)` | end the run as failed |

The target is positional, and its keyword arguments are bound against its signature *at
transition time* — a typo in a parameter name fails on the transition that made it, not
three states later as a missing key.

`Await` is a portable polling loop (`WORKHORSE_AWAIT_POLL_S`, default 15s), not an
inotify watch, so it behaves the same in a container, over NFS, and on a laptop that
sleeps. The checkpoint is written **before** the wait begins, so a machine rebooted
during a two-day wait resumes into the waiting state rather than re-asking.

## Checkpoints and renaming

The checkpoint is `(state, params)` plus the frozen inputs and `ctx`, tagged
`"engine": "pyflow"`. Resume is deliberately **coarse**: it re-enters the checkpointed
state from the top, with no intra-state memo and no per-callsite fingerprinting. That
makes idempotency — not merely determinism — the contract a state body owes. A state
that appends a row should check first; a state that commits should be a no-op on a
clean tree.

Because a checkpoint names a state, renaming one strands every run checkpointed on the
old name. Both decorators take `aliases=[…]` for exactly that:

```python
@workflow.state(aliases=["qa_gate"])
def qa(self, story: str): ...
```

A checkpoint naming an unknown state **fails loudly** rather than silently starting the
run over; declaring the old name as an alias resumes it; an alias that collides with a
live name raises at import; and `dot` / `--dry-run` render live names only, so an alias
never shows up as a second state in a diagram. `@blueprint.node` takes `aliases=[…]` for
the same reason — `self.output(node)` resolves against a run directory named after the
node.

A checkpoint left behind by the retired YAML engine is refused by name rather than
misread: it shares the runs directory and `--resume-latest` with live runs, and a node
id that happens to match a state name would otherwise resume the wrong thing.

## The node index is the substitution seam

`self.call(measure, ...)` takes the function object because that is what makes the call
type-check — the argument list is `measure`'s own. But what *runs* is whatever the run's
node index holds under `measure`'s registered name. `Registry.add_blueprints(...)` folds
every blueprint's nodes into that one index, and the run is handed it as a field of its
environment. So the registry is a **composition root**: a node is resolved by name, from a
table the caller supplies, rather than by dereferencing the module attribute the state
happened to import.

A node the index does not carry is a hard error naming `add_blueprints`, not a silent
fallback — which is what finally gives the collision detection teeth.

Three ways to put something else in the table:

```python
# 1. declared at authoring time — what --dry-run returns for this node
@blueprint.node(stub=lambda logger, subject: Reading(kind="stub", count=0))
def measure(logger, subject: str) -> Reading: ...

# 2. declared on the registry — what --dry-run returns for an agent turn,
#    keyed by prompt stem (hyphens, hence a dict rather than **kwargs)
workflow = Registry("acme").add_blueprints(blueprint).stub_agents(
    {"review": {"ok": True}}
)

# 3. supplied by one run — a copy of the index with those names rebound
env = RunEnv(..., nodes=workflow.override(measure=lambda logger, subject: Reading(...)))
```

`override` is non-mutating: it returns a copy, so a substitution belongs to the run that
asked for it and cannot leak into the next one.

**That is what a test uses instead of patching.** The research workflow's tests used to
reach into two module namespaces and put them back afterwards:

```python
# before — monkeypatching, with a finally-restore to remember
pyflow_engine.agent_ladder.run_agent = agent
with patch("workhorse_workflows.research.nodes.setup.allow_all_directories"):
    ...
```

```python
# after — the same two dependencies, handed to the run
RunEnv(
    ...,
    agent_runner=agent,
    nodes=research.workflow.override(
        clone_repo=lambda logger: RepoSetup(repo_dir=str(repo))
    ),
)
```

Nothing else in the workflow is substituted: the real `load_program` and
`publish_results` run against a temporary git repo. The point is not fewer stand-ins, it
is that the two there are cannot outlive the run — there is no global to restore and no
ordering between tests to get wrong.

A **sub-flow does not inherit any of this.** `handoff` resolves the child class's own
registry (stamped on the class when it is registered) and swaps `workflow_dir`, `nodes`
and `agent_stubs` together, so a child renders prompts from its own package and calls its
own nodes — a parent's override stops at the boundary. A class with no registry of its own
keeps the parent's world, which is what same-module sub-flows want.

## Labels, and saying what the run is doing

A workflow declares its telemetry dimensions by overriding `labels()`. It takes no
arguments and is re-read before every transition, so
it reads whatever the instance can already see — inputs, `self.ctx`, and `self.output(node)`
for anything a node recorded:

```python
    def labels(self) -> dict[str, str]:
        try:
            return {"work_id": self.output(select_next_unit).unit_id}
        except NodeNotRunError:
            return {"work_id": ""}
```

Values that render empty are dropped rather than stamped blank, and a `labels()` that
raises costs the labels for that transition and nothing else — never the run.

These keys are **not** `wf.`-prefixed. The retired YAML engine prefixed them so a
workflow could not shadow an OTel convention; here the collector reads the unprefixed
spelling, and nothing is translated on the way out. Both spellings are still promoted
onto the live gauges, so spans already in a store keep reaching a dashboard untouched.

**Activity — what the run is working on right now — is a flagged log record**, not a
field:

```python
    def assess(self, unit_id: str):
        self.logger.info("assessing %s", unit_id, extra={"activity": True})
```

The rendered message *is* the activity: `activity` is a flag, not a value, so the text is
never written twice and never drifts from what the log says. It is a log record rather
than a declared field because a state is one method that may do several things and the
interesting one is whichever it is doing now — and a `@blueprint.node` is a plain function
with no `self`, so its injected `logger` is the only route it could have. Both are the same
logger object, so both work identically.

It is **sticky**: the last flagged line stands until another replaces it, so a state that
flags once and then works for an hour stays correctly labelled. Nothing flagged yet falls
back to the node id, which the gauges stamp anyway.

