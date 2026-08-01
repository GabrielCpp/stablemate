---
type: format
slug: workflow-format
title: The workflow format (a Python package)
---
# Workflow format

A workflow is a **Python package**, not a file. It declares a `Registry` under a name, the
`Workflow` subclasses whose methods are its states, and the `@blueprint.node` functions
that do its work; its distribution binds that registry to a command in
`[project.scripts]`, which is how [`workhorse-<name> run`](workhorse.md#run) reaches it.
There is no file to hand the CLI and no schema to validate — the package *is* the format, and
Python's own import and signature machinery is what checks it. Why it is a package rather
than a declarative file is argued once, in
[workhorse/README.md](../../../workhorse/README.md#why-a-workflow-is-python-and-not-a-config-file).

This page is the **structural reference**: what a workflow package contains and what each
piece must be. The narrative guide to writing one — worked examples, the three tiers of
state, the substitution seam, telemetry labels — is
[workhorse/docs/AUTHORING.md](../../../workhorse/docs/AUTHORING.md). Holding a
`workflow.yaml` from the retired YAML front-end? Every construct in that schema is mapped
to its replacement in
[workhorse/docs/WORKFLOW.md](../../../workhorse/docs/WORKFLOW.md); the schema itself is
gone, along with its loader, its node model and its `script`/`branch`/`call` runners.

## Package layout

```
my_workflow/
├── __init__.py
├── workflow.py         # the Registry, the Workflow classes, the console script
├── nodes.py            # @blueprint.node functions
└── prompts/            # Jinja2 .md templates
    └── step.md
```

Nothing enforces those filenames — the console script names whatever module holds the
`main` it points at, and prompt paths are resolved relative to the package directory. What
*is* load-bearing is that the package be importable from a real directory on disk:
`Registry.directory()` refuses a zip-imported package, and [`run`](workhorse.md#run) calls
it eagerly so that failure arrives at startup rather than at the first prompt render.

## Fields

### Registry
- type: `workhorse.pyflow.Registry` — required: yes

The composition root, and the object the console script carries. It carries the
workflow's name, its node index, its named flows and its agent stubs; handing
`console_script` anything else — a bare name, most of all — is a `TypeError` naming what it
actually got.

```python
workflow = Registry("acme").add_blueprints(blueprint)
main = console_script(workflow.entry_point(Build))
```

- `add_blueprints(*blueprints)` — folds every blueprint's nodes into the one index a run
  is handed. A node the index does not carry is a hard error naming `add_blueprints`, not
  a silent fallback.
- `add_flows(**flows)` — names re-entry points (`add_flows(qa=Qa, dev=Dev)`), each value a
  `Workflow` subclass. Those names are what `workhorse-<name> run <flow>` accepts.
- `override(**by_name)` — returns a **copy** of the index with those names rebound. Used by
  tests; non-mutating, so a substitution cannot outlive the run that asked for it.
- `stub_agents({stem: reply})` — declares what `--dry-run` returns for an agent turn, keyed
  by prompt stem.
- `entry_point(entry)` — declares the flow a bare `run` starts, and returns `self` so it
  composes with the binding below: `console_script(workflow.entry_point(Build))`.
- `directory()` — the package directory prompts resolve against.

### console script
- type: `[project.scripts]` entry — required: yes

The only way a workflow is reached. `console_script(registry)` returns the callable the
script points at — returned rather than called, because a script target is imported and
*then* invoked — and that callable carries the `Registry` itself, so nothing is resolved by
name and nothing is found by path:

```python
main = console_script(workflow.entry_point(Build))
```

```toml
[project.scripts]
workhorse-acme = "acme_workflow.workflow:main"
```

Without the `[project.scripts]` row the package is still importable and still testable —
it just has no command. Workhorse ships no executable to run it with instead.

### Workflow subclass
- type: `workhorse.pyflow.Workflow` subclass — required: yes (at least one)

The state machine. Its **inputs** are class attributes (a pydantic model's fields), filled
from `--params` and frozen once `setup()` returns. Its **states** are methods. The entry
state is the method named `start` — not a declared key, and not the first method defined.

```python
class Build(Workflow):
    subject: str                       # input — required, from --params
    target_env: str = "local"          # input — optional, with a default

    def setup(self) -> Settings:       # runs once; its return becomes self.ctx
        return Settings.load(self.subject)

    def start(self):
        return Continue(None, self.review, count=0)
```

- `setup()` — optional; runs once before the first state, and its return value becomes
  `self.ctx` for the whole run.
- `labels()` — optional; returns `dict[str, str]` and is re-read before every transition.
  Keys are **not** `wf.`-prefixed. Values that render empty are dropped; a `labels()` that
  raises costs that transition's labels and nothing else.
- `self.call(fn, …)` / `self.agent(path, returns=…, args=…, power=…, timeout=…, cwd=…,
  add_dirs=[…])` / `self.handoff(Child, **inputs)` / `self.output(node)` — the four things
  a state body does. `self.output(node)` is a *read* of a recorded artifact and raises
  `NodeNotRunError` when the node has not run.

### state
- type: method on a `Workflow` subclass — required: yes (`start`, at minimum)

An ordinary method. Its parameters are the state parameters the previous transition bound;
they live exactly one hop. Control flow inside it is ordinary Python — `if`, `for`, a
counter that is just a counter. It must return a transition (or raise `WorkflowFailed`).

`@workflow.state(aliases=[…])` declares former names for a state, so a run checkpointed on
the old name still resumes. A checkpoint naming an unknown state fails loudly rather than
silently restarting the run; an alias colliding with a live name raises at import; and
`dot`/`--dry-run` render live names only.

### transition
- type: `Continue` · `Done` · `Await` — required: yes (every state returns one)

| Return | Meaning |
|---|---|
| `Continue(result, self.next_state, **params)` | go to `next_state` with those parameters |
| `Done(result)` | this flow is finished; `result` is what a `handoff` caller receives |
| `Await(path, questions, self.next_state, **params)` | write `questions` to `path`, checkpoint, and poll until a human touches the file |
| `raise WorkflowFailed(reason)` | end the run as failed |

The target is **positional-only**, and the keyword arguments are bound against its
signature *at transition time* — a typo in a parameter name fails on the transition that
made it rather than several states later as a missing key.

### Blueprint
- type: `workhorse.pyflow.Blueprint` — required: no

Collects `@blueprint.node` functions under a namespace, to be folded into a registry.

```python
blueprint = Blueprint("acme")


@blueprint.node
def measure(logger, subject: str) -> Reading:
    return Reading(kind=subject, count=len(subject))
```

### node
- type: function decorated with `@blueprint.node` — required: no

A plain function whose **first parameter is `logger`**. Its declared return annotation is
its output contract — a `BaseModel`, or any JSON-able value — and that is what gets
recorded as the node's artifact. It runs in the driver's own process: there is no
subprocess, no stdout protocol, and no JSON to print. It imports its libraries at module
scope, because an installed distribution's dependencies are resolved by `pip`/`uv` before
a run exists to fail.

`@blueprint.node(stub=…)` declares what `--dry-run` substitutes for it;
`@blueprint.node(aliases=[…])` declares former names, because `self.output(node)` resolves
against a run directory named after the node.

### prompts/
- type: directory of Jinja2 `.md` templates — required: no (yes if any state calls `self.agent`)

Resolved relative to the package directory. Rendered with a resilient undefined — a
missing variable renders empty and logs a warning rather than raising. `node_timeout_s` /
`node_timeout_min` are injected so a prompt can size its own work (both read `"unbounded"`
when the turn has no budget). A prompt must output JSON matching the model its turn
declared in `returns=`.

The render context is the [context manifest](context-manifest.md) underneath and the
state's `args` on top — so a state that binds `repo` means its own, not the manifest's.
Those `args` go into the context as **real Python objects**, not as pre-rendered strings:
an `int` stays an `int` and a `Path` stays a `Path`, which is the one place prompt
rendering genuinely differs from the retired engine (whose `args:` was a dict of Jinja
template strings, and so stringified everything on the way past).

## The agent turn

One LLM turn, in its own session, driven by the [agent backend](concepts/agent-backend.md)
`--cli` selected. The state calls it, gets a typed value back, and decides what to do — the
turn itself is not a graph node and has no `next:`:

```python
verdict = self.agent(
    "prompts/review.md",              # the template, relative to the package
    returns=Verdict,                  # the model the reply must satisfy
    args={"unit": unit_id},           # rendered into the prompt
    power="medium",                   # the abstract tier the config maps to a model
    timeout=1800,                     # this turn's wall-clock budget, seconds
    cwd=self.ctx.repo_root,           # where the CLI is launched
    add_dirs=[self.ctx.docs_root],    # further directories it may read
)
```

Every keyword past `returns=` is optional and defaults to whatever the engine defaults to,
so a state that says nothing behaves as before. These are **real Python values, not
template strings** — the state computes them and passes them.

Underneath, the turn goes through [`render`](concepts/render-prompt.md), the
[resilience ladder](concepts/run-agent.md), and [output
extraction](concepts/extract-outputs.md), all unchanged by the port.

### returns
- type: a pydantic `BaseModel` subclass — required: yes

The reply contract, replacing the retired schema's per-key `outputs:` list. The turn's JSON
is validated into this model, and its fields are what the state reads. When the resilience
ladder exhausts every recovery, it emits **this model's declared keys as nulls** rather
than crashing the run — so a state branching on an agent reply needs a safe arm for the
empty one. `AGENT_USE_DEFAULT_OUTPUTS=false` hard-fails instead.

### power
- type: `str` — required: no — default: the backend's own default tier

An abstract tier (`low` / `medium` / `high`), resolved per backend through
`~/.config/stablemate/config.toml` at `power.<tier>.<backend>` into a concrete model and
reasoning effort. A workflow names the tier it needs; the operator's config decides what
that costs. See [BACKENDS.md](../../../workhorse/docs/BACKENDS.md).

### timeout
- type: `float` (seconds) — required: no — default: `3600` (one hour)

This turn's wall-clock budget. Pass `float("inf")` for a turn that must not be cut off;
be deliberate about it, because an unbounded turn that wedges hangs the run with no
timeout-retry recovery. The effective value is injected into the prompt context as
`node_timeout_s` / `node_timeout_min` so the prompt can size its own work; both read
`"unbounded"` when the turn is unbounded.

### cwd and add_dirs
- type: `Path`-like, and a list of `Path`-like — required: no

`cwd` is where the agent CLI is launched, which decides whose `CLAUDE.md`, skills and git
context the turn sees — it matters more than it looks. `add_dirs` are further directories
the turn may read; the runner de-dupes them against `cwd` and turns the rest into
`--add-dir` flags.

## What has no counterpart

The retired schema had three constructs with no Python spelling. Each is a consequence of
what the port bought rather than an oversight, and each is spelled out with its reasoning
in [WORKFLOW.md](../../../workhorse/docs/WORKFLOW.md#what-has-no-counterpart):

- **`requires:`**, the tool preflight — a workflow is an installed distribution now, so its
  dependencies are `[project.dependencies]` and are resolved at install time.
- **`default:` on an OutputSpec** — the resilience ladder still defaults an exhausted agent
  turn, but emits the `returns=` model's keys as nulls rather than guessing a value.
- **per-node `activity:`** — now a flagged log record
  (`logger.info(…, extra={"activity": True})`), so the rendered message *is* the activity.

## Related

- [workhorse CLI](workhorse.md) — the commands that resolve and run a workflow
- [drive](concepts/pyflow-driver.md) — the state loop that walks the machine
- [state graph](concepts/pyflow-state-graph.md) — what `dot` and `--dry-run` derive from it
- [run artifacts](run-artifacts.md) — what a run writes as it goes
