# Writing a workflow

This is the authoring reference for workhorse workflows: the package layout, the three
tiers of state, transitions, checkpoints and aliases, the node index that tests substitute
through instead of patching, and the labels that tell a collector what a run is doing.

It assumes you can already run a workflow. If you cannot yet, run the shipped quick start
first — it needs no repository and, under `--dry-run`, no agent CLI at all:

```bash
workhorse-hello-world run --dry-run
```

Its whole source is one commented ~90-line file,
[`workflows/src/workhorse_workflows/hello_world/workflow.py`](https://github.com/GabrielCpp/stablemate/blob/main/workflows/src/workhorse_workflows/hello_world/workflow.py),
carrying one of each thing this document describes: a node, two states, an agent turn and
a registry. **Copy its directory** — that file plus the `prompts/` beside it — and edit
the copy; every example below is a variation on it. Copying `workflow.py` alone leaves the
agent turn with no template, and a dry run says so before it runs anything:
`state 'greet' renders 'prompts/greet.md', which does not exist`.

Which is the habit to form: `--dry-run` is the check to run after **every** edit below, not
only the first. Before it drives anything it reads your states' own source and fails on a
prompt path that does not resolve, a state unreachable from the start state, a transition
naming something that is not a state, and a machine no state can end. That is the
branch-independent half of correctness, and one run down one path cannot cover it.
[CHECKING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/CHECKING.md)
is what each finding means, and when reaching a failure terminal is one.
[README.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/README.md) covers
install and the CLI in full. The resilience knobs the failure paths below land in are
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

`nodes.py` there is a *split*, not a requirement — `hello_world` keeps its one node in
`workflow.py`, and when the split stops being taste is
[workflows/README.md](https://github.com/GabrielCpp/stablemate/blob/main/workflows/README.md#layout),
where that rule is stated normatively. `prompts/` is not optional in the same way: a state
that renders a template needs the template on disk beside its package.

Its **states** are methods on a `Workflow` subclass, each returning the next state;
its **nodes** are plain functions collected into a `Blueprint`; a `Registry` names the
whole thing and is what the package's console script is built from. Control flow
is ordinary Python — `if`, `for`, a counter that is just a counter.

## Shipping your own, outside this repo

Workhorse is a library: it ships no command, resolves no workflow by name, and scans no
directory. A workflow reaches a terminal by **declaring its own console script**, so a
workflow of your own is a distribution, and this is the whole of it:

```toml
# acme-workflows/pyproject.toml
[project]
name = "acme-workflows"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["workhorse-agent"]

[project.scripts]
workhorse-greeter = "acme_workflows.greeter.workflow:main"   # what console_script RETURNED

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/acme_workflows"]
```

Two details are load-bearing rather than taste:

- **The script names what `console_script(...)` returned, not a call to it.** A
  `[project.scripts]` target is called after import, so the module needs a module-level
  `main = console_script(workflow.entry_point(Greeter))`; `console_script(...)()` would
  drive a run at import time instead of binding a command. A workflow with no row in this
  table has no command at all — which you notice at install time, not mid-run.
- **It must install unpacked, with the prompts inside it.** Prompts are rendered by a
  filesystem template loader rooted at the package directory, so a zip-imported install is
  refused, and a `prompts/*.md` left out of the wheel is a workflow that starts and then
  cannot render. The `[tool.hatch.build.targets.wheel]` above needs nothing further —
  hatchling ships every file under `packages=`, markdown included — but a backend that
  takes only `.py` unless told otherwise (setuptools without `package_data`) will drop
  them. Do not set `zip-safe`-style options either way.

Then install it **into workhorse's own interpreter**, because a workflow's code and its
tools are imported in-process:

```bash
uv pip install ./acme-workflows       # or: pipx inject workhorse-agent ./acme-workflows
uv run workhorse-greeter run --dry-run
```

Copying `hello_world/` and changing the `Registry("hello-world")` name and its
`[project.scripts]` row is the shortest route to a green run of your own; everything below is what you add next.

**Agent prompts** must output JSON matching the model the turn declared in `returns=`:

````markdown
Do the thing.

Output JSON only:

```json
{"status": "ok", "count": 5}
```
````

## Unattended resilience (waiting, then a clean stop)

Runs are meant to survive a week without supervision, so the runner absorbs what it can:
transient retries whose budget is measured in **days**, cap waits that sleep until the
window reopens, and prompt reframing (see
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md)).

What it will **not** do is answer for a node. When every layer is spent the run stops at
its checkpoint and waits for an operator. So a state never receives a reply whose fields
the agent didn't produce, and never needs a branch for one — if `self.agent(...)` returns,
the model said it.

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

`self.agent` takes six optional keywords beyond the prompt, all defaulting to "whatever
the engine defaults to", so a state that says nothing behaves as before:

```python
review = self.agent(
    "prompts/review.md",
    returns=Verdict,
    args={"unit": unit_id},
    power="medium",                       # the abstract tier the config maps to a model
    timeout=1800,                         # this turn's wall-clock budget, seconds
    retries=0,                            # this node's own reframe budget
    cwd=self.ctx.repo_root,               # where the CLI is launched
    add_dirs=[self.ctx.docs_root],        # further directories it may read
)
```

`cwd` matters more than it looks: it decides whose `CLAUDE.md`, skills and git context the
turn sees. The runner de-dupes `add_dirs` against it and turns the rest into `--add-dir`
flags.

`retries` overrides the run's `AGENT_MAX_REPHRASE_ATTEMPTS` for this node alone — how many
times a failed turn is re-asked from scratch in a fresh session before the ladder gives up.
Pass `0` when the turn's **deliverable is a file rather than its reply** and this state can
read a partial one back: a reframe discards the session and re-asks at full price, which
buys nothing the state could not get more cheaply by reading what is already on disk — and
under a tight `timeout` it multiplies that budget by the number of reframes before the run
stops. Whether a partial artifact is worth something is only knowable here, which is why
this is a per-node keyword and not a run-level setting.

Such a node usually wants to *land* an overrun too, and `AgentTimeout` is the name it
catches to do so — raised by `self.agent` once the ladder has finished with a turn its
`timeout` cut, so catching it is not short-circuiting a retry that would have worked.
Only the wall-clock overrun is translated; a crashed CLI still ends the run, because a
state that confused the two would repair a file the turn never wrote:

```python
try:
    self.agent("prompts/plan.md", returns=Plan, timeout=1200, retries=0)
except AgentTimeout:
    pass                                  # the partial draft on disk is the deliverable
return Continue(None, self.validate)      # …which the next state reads and repairs
```

These are **real values, not templates**: the state computes the path in Python and
passes it. (They are still Jinja-rendered on the way through, so a literal path is a
no-op render and a template string would also work — but nothing needs one.)

## Session chains (`session=`), for a loop that repairs its own work

The default is one clean context per turn: the engine unlinks `.session_id` before each
node, so a reviewer never inherits the author's reasoning and a node re-entered after a
resume opens on the state as it is, not as the last attempt imagined it. That default is
right almost everywhere, and this keyword is the deliberate exception.

A **repair loop** — verify, repair, verify again — breaks under it. Lap two is handed the
same worklist as lap one and has to re-derive everything lap one already found before it
can do any new work: the file it edited, the fix it tried, the hypothesis it eliminated.
That is a full turn of reading bought to end up with a worse copy of the context the
model had a minute ago, and it is why such a loop can run its budget out without
converging.

Naming a **chain** keeps those laps in one conversation:

```python
self.agent(
    "prompts/repair.md",
    returns=Repair,
    session=f"docs-repair:{story.slug}",   # laps share one conversation
)
```

Turns sharing a key resume each other. The id lives in `<run_dir>/.sessions/<key>` rather
than `.session_id`, so a chain and the ordinary clean-context nodes cannot overwrite one
another, and a chain survives the other nodes running between its laps.

**Key it per worklist, not per node and not per run.** `docs-repair:STORY-4` is right;
`docs-repair` is not — two stories repaired in one run would share a conversation, and
story two would open on story one's diff.

End a chain explicitly when the conversation stops being an asset:

```python
self.reset_session(f"docs-repair:{story.slug}")   # next turn on this key starts fresh
```

The rules that matter, all of them cases where continuing costs more than it saves:

- **On entering and leaving the flow** — so a re-entered flow does not resume a
  conversation about a version of the work that no longer exists.
- **When the loop stalls** — two laps that changed nothing mean the conversation has
  talked itself into a corner, and a fresh context is the cheapest way out.
- **After a few laps** (four is the number the coder workflow uses) — a chain that long
  is mostly compaction, and its remaining value is smaller than its cost.
- **When the worklist is rebuilt from scratch** — the context describes the old one.

What does *not* get a chain: planning, drafting, reviewing, and any node whose whole
point is an independent judgement. A reviewer that remembers arguing for the change it
is reviewing is not a reviewer.

Two things are handled for you. A chain whose session the CLI will not resume — expired,
pruned, or copied in from another machine — is dropped and re-run once on a fresh
session, logged as `chain <key>: session not resumable, starting fresh`; it costs no
retry and no reframe, because nothing about the node was wrong. And a chain's laps
compact rather than restart, so the context-overflow layer of the ladder applies to the
conversation as a whole.

The chain is in the telemetry too: the node's `enter` record carries `chain` and the
`resumed_session` it continued, so a reader can tell a lap that resumed from one that
started over without joining three files by hand.

## A stack that outlives the turn (`workhorse.stack`)

A process an agent turn backgrounds is dead by the next state — the runner reaps the
turn's process tree. Anything that must survive across states (a dev server, a compose
stack, an emulator) is therefore brought up by a `script` node calling
`workhorse.stack.ensure_stack`, and reaped by `teardown_stack`. Both take a **manifest
dict** the workflow supplies, so the primitive stays workflow-agnostic:

```python
status = ensure_stack(manifest, repo_root=self.ctx.repo_root, logger=log)
```

| Key | What it does |
|---|---|
| `entry_url` / `health_path` | the HTTP readiness probe (path defaults to `/`) |
| `identity` | a substring expected in the served **response body** — the readiness signal, and a precondition for reuse |
| `reuse` | when adopting an already-serving stack is safe: `if-fresh` (default), `always`, `never` |
| `fresh` | a probe command (exit 0 ⇔ the running stack reflects current code) that gates `if-fresh` adoption |
| `app_cwd` / `repo_root` / `boot_timeout` | launch context, and the ceiling on boot |
| `launch` / `stop` | the **idempotent** bring-up command, and the teardown recipe (absent ⇒ leave an expensive stack up) |
| `prepare` / `seed` / `health` | ordered steps run before launch / after it serves / last |
| `health_timeout` | the window in seconds the `health` gates get to converge (default 120) |

**Every command in the manifest is a shell recipe**, run through `bash -c` (`/bin/sh -c`
only where there is no bash) — `launch`, `stop`, and each `prepare`/`seed`/`health` step.
Pipes, `&&`/`||` guards, redirection and `&` all mean what they say, which is what makes
the *idempotent* launch above expressible at all: "start it unless it is already serving"
is written `<probe> || <start>`, and a bring-up command that hands the stack off writes
`nohup … & disown`. bash rather than `sh` because `sh` is dash on Debian/Ubuntu and dash
has no `disown`.

**`identity` is matched against the response body — not the URL, host or port.** It is
the one manifest key whose mistakes are invisible to the obvious hand-check: `curl -sf -o
/dev/null <url>` discards the body, so a URL that answers 200 to every manual probe still
fails the gate when the marker is not in what it served. Pick something the page really
says (a `<title>`, a health endpoint's `"status":"ok"`), or omit the key — omitted means
"any 2xx/3xx is ready", which also disables adoption, since adopting an arbitrary listener
on that port is exactly what the marker exists to prevent. Setting it to a host:port is
the recurring mistake; that string is in the *request*, never the response.

**Health gates retry inside that window.** Booting proves only that the entry URL
answers, and a gate typically asserts on a *slower sibling* — a migration, a queue, a
second container. A gate that fails is re-attempted every few seconds until
`health_timeout` expires, so a multi-service stack is not failed for coming up in the
order it always comes up in.

`ensure_stack` returns `{ready, adopted, entry_url, app_pid, app_pgid}`, plus
`failed_step` and **`error`** when it could not get there. `error` is the failing step's
own message, and it is there because a caller's usual next move is to hand the failure
to whoever repairs it: the step name alone ("the health gate") says which thing broke,
not what to fix. Log lines don't cross the node boundary — the return value does. For
`failed_step: "launch"` that message is bring-up's *own* verdict — nothing answering, a
recipe that would not spawn, a nonzero exit, or the `identity` mismatch above — and not a
single sentence blaming the launch command for all four.

Nothing here raises. A stack that will not come up returns `ready: "no"`, which is what
lets the workflow decide between repairing, re-planning and asking an operator.

## Transitions

A state returns one of three things, or raises:

| Return | Meaning |
|---|---|
| `Continue(result, self.next_state, **params)` | go to `next_state` with those parameters |
| `Done(result)` | the flow is finished; `result` is what a `handoff` caller receives |
| `Await(path, questions, self.next_state, **params)` | write a canonical `STATUS: AWAITING_OPERATOR` gate to `path`, checkpoint, and wait for a human to touch the file; blank questions preserve a gate another node already authored |
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

**A sub-flow resumes too.** A `handoff` writes the child's own checkpoint under
`<run>/<flow-node>/_flow/`, and a resume that re-enters the handoff state continues the
child from it — a run killed six states into the QA flow does not replay them. The child
is only continued when it is the flow the run was *inside*: the checkpoint has to name
the same class and carry the same inputs, and the offer expires with the resumed state,
so a loop that hands off to the same flow once per story still starts each story's child
clean. Anything that disagrees starts fresh with a line in the log, never an error.

*Clean* means the scope directory is emptied, not just its checkpoint dropped. Every
iteration re-enters the same `<run>/<flow-node>/_flow/`, so leaving the last story's
per-node folders there would hand the next story its answers: `self.output(node)` is a
file lookup whose contract is "`None` when it has not run", and a state asking for a node
this pass never reached cannot tell a stale hit from a fresh one. The genuine mid-flow
resume above is the one re-entry that keeps the directory, which is why it is keyed on
the engine's "we died inside this node" signal rather than on a checkpoint merely being
present.

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

A workflow declares its telemetry dimensions by overriding `labels()`. It is re-read
before every transition, so it reads whatever the instance can already see — inputs,
`self.ctx`, and `self.output(node)` for anything a node recorded:

```python
    def labels(self) -> dict[str, str]:
        try:
            return {"work_id": self.output(select_next_unit).unit_id}
        except NodeNotRunError:
            return {"work_id": ""}
```

Values that render empty are dropped rather than stamped blank, and a `labels()` that
raises costs the labels for that transition and nothing else — never the run.

### Reporting which attempt this is

For a dimension that depends on the arguments the *next state* was bound with, override
`state_labels(params)` instead. It defaults to `labels()`, so overriding either one alone
is enough.

```python
    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        loop = params.get("loop")
        if loop is None:
            return self.labels()
        return self.labels() | {"plan_rework": str(loop.plan_rework)}
```

This is how a bounded retry budget reaches telemetry, and it needs no bookkeeping in the
states themselves. A budget is almost always already a state parameter — it has to be,
since state parameters *are* the checkpoint — so the count is in hand at exactly the
moment the labels are read. The alternative, having each state assign its counter to
`self` for `labels()` to find, means one edit site per state and instrumentation that is
silently wrong wherever it was forgotten.

It is a second hook rather than an argument to `labels()` because a subclass cannot add a
parameter its base does not declare without breaking every caller of the base — the type
checker rejects it, and rightly.

It is worth the trouble because a label is stamped on **every** span opened while it is
current — the node spans and the `agent_turn` span alike. So a query can group cost by
attempt number directly. Without it, a span from the third repair pass is
indistinguishable from the first, and "how many attempts did this unit spend, and where"
cannot be answered from the trace at all.

Keep the values low-cardinality; a bounded counter is ideal, a free-text note is not.
The engine passes the dict it already holds and never inspects it — what counts as a
dimension stays the workflow's call.

### Nodes that wait on infrastructure

Not every node span is work. `ensure_stack` brings an app stack up and health-gates it,
which on a real run is minutes of waiting with the model idle — and in an aggregate over
node duration that is indistinguishable from minutes of effort.

A workflow says which of its own nodes those are:

```python
class Qa(Workflow):
    INFRA_NODES: ClassVar[frozenset[Any]] = frozenset({ensure_stack})
```

Their spans carry `workhorse.span_kind="infra"`; every other node carries nothing, so
"the workflow did not classify this" stays distinct from "the workflow called it work".

It is declared, never inferred. Workhorse is a generic driver and must not learn what a
node *means* from its name or module — the workflow already knows which of its own nodes
do infra work, the same way it already knows its own `labels()`.

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
