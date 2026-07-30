---
type: feature
slug: workflow-as-python-state-machine
title: Workflows as Python — a flow-level state machine
status: design
---
# Workflows as Python — a flow-level state machine

> **Related:** [workflow-format](../features/workhorse/workflow-format.md) (the YAML contract this
> would replace) · [run-artifacts](../features/workhorse/run-artifacts.md) (the checkpoint/resume
> substrate that survives) · [workhorse-otel](workhorse-otel.md) (span/log emission, unaffected) ·
> **[author-workflow-python/](author-workflow-python/)** (the whole `author` workflow rendered in
> this shape — the artifact that settled most of what follows).
> This is a pre-implementation design brief. Nothing below is built.

Status: **design** (2026-07-29). Reached by working through three candidate shapes; the third is
the one to build. No code written, no migration started.

A second pass then rendered `base-library/workflows/author/` — 2,389 lines of YAML over 159 nodes,
plus 23 scripts totalling 2,650 — into the proposed shape, and that exercise moved four things:
the flow/node split became a **class/blueprint** split, typed payload models were **removed**,
`handoff` was **un-rejected** with a narrower meaning, and waiting on a human became a
**transition** rather than a blocking call. Sections below are marked where they were revised.

## The proposal in one paragraph

A workflow stops being a `workflow.yaml` walked by the `workhorse` CLI and becomes an **executable
uv project** that imports workhorse as a library. A workflow is a **class**; its methods are the
states; the body of a method uses native `if`/`for` over real values; and the *transition between
states* is an explicit value returned to an engine driver loop. Nodes — the durable, recorded,
observable steps — are free functions collected in **blueprints** that a workflow composes in. The
result is a state machine whose states are methods and whose interiors are ordinary Python.

## Why change anything

The YAML is not failing at expressing graphs. It is failing at expressing the two things a graph
does not model: **values** and **loops**.

`base-library/workflows/research/workflow.yaml:40-48` is the honest evidence:

```yaml
max_reworks: "3"
# Enforced as literals in the guard branches below (branch condition values
# can't be Jinja), so keep these comments in sync if you change the literals
```

A constant that cannot be a constant, kept in sync with its three use sites by comment. Downstream
of it, `init_lead_counter`, `init_extend_counter`, `reset_rework`, and `guard_rework` — four nodes
plus three scripts — exist only to emulate `for _ in range(3)`. And every value crossing a node
boundary is a Jinja string (`AgentNode.args` is `dict[str, str]`), so nothing between nodes is
checkable.

The scale this happens at: 7,992 lines of workflow YAML across four workflows, of which
`coder/workflow.yaml` alone is 4,366.

A second, independent motivation: **dependency isolation**. A `script:` node imports `ostler` from
*workhorse's own interpreter*, which is why `pipx inject workhorse-agent ostler` appears in the
README and why the isolated-tools install cannot run a base-library workflow at all. If a workflow
is a uv project with its own `pyproject.toml`, `uv` resolves its deps and workhorse is merely one
of them. This is arguably a bigger win than the syntax.

## What the engine actually is today

Relevant because it bounds the cost. YAML is a thin front-end:

| Component | Lines | Fate |
|---|---:|---|
| `graph/loader.py` (YAML → `Graph`) | 45 | deleted |
| `graph/nodes.py` (Pydantic node model) | 256 | deleted |
| `graph/dot.py` | 297 | rewritten against the new model |
| `graph/context.py` | 41 | survives in spirit |
| `main.py` (CLI + `_step_loop` + resume) | 1,565 | driver loop reworked, much reused — see below |
| `runner/*` (agent backends, guardrail ladder) | — | untouched |
| `templates.py` (Jinja render + farrier globals) | 237 | untouched — see below |
| `artifacts.py`, `otel.py`, `scriptutil.py`, `stack.py` | — | untouched |
| `testing.py` | 575 | mostly unnecessary; a flow becomes a function you call |

`runner/call.py` already dispatches to registered Python functions via `builtins.REGISTRY`, and
`runner/script.py`'s `InProcessScriptRunner` already imports library Python and calls its
`main(logger)` in the engine's process. The "library is data, not code" line was crossed some time
ago; this proposal makes it explicit rather than crossing it anew.

### Prompt rendering is workhorse's, and none of it changes

Stated explicitly because the rest of this document does not touch it, and a reader could
reasonably assume packaging moves it.

**Workflows are not installed into the consuming repo.** They run directly from the library, and
`workhorse` renders their prompts with Jinja **at run time** — `templates.py:render()` builds a
`FileSystemLoader` rooted at `workflow_dir` and injects the farrier helpers
(`instruction_ref`/`prompt_ref`/`skill_dir`/`template.*`) as Jinja globals resolved against the
live context, per `_farrier_globals`. What the repo contributes is data, not a copy of the
workflow:

- `.agents/agents-context.json` — the per-repo **context manifest** farrier emits, merged into the
  workflow context under `_instructions` / `_prompts` / `_used_skills` / `_skill_dir`. This is how
  a library-resident prompt names a skill without knowing where that repo installed it.
- `.agents/flavors/<workflow>/<node>.md` — a per-node prompt **override**, rendered instead of the
  base with the base still on the loader path so its `{% extends %}` resolves.

Four consequences for the packaging flip:

1. **The prompt contract survives untouched.** Prompts stay beside their flows and are read
   through `workflow_dir`; a flow's `workflow.agent("prompts/plan.md", …)` resolves exactly as a
   YAML node's `prompt:` does today. There is no install-time render step to relocate, because
   there is no install.
2. **The per-repo override is already finer than a library layer.** A repo changes one prompt with
   a flavor file — it never forks a workflow to do it. So moving workflows out of the layer stack
   costs nothing here; the mechanism operators actually use is on the repo side.
3. **farrier stops reading workflow prompts entirely** — see the next section. An earlier draft of
   this document claimed that edge outlives the flip; it does not, and it barely exists today.
4. **`workflow_dir` must remain a real directory.** `FileSystemLoader` cannot read a zip, and
   `_flavor_override` keys the flavor lookup on `workflow_dir.name`. A packaged workflow therefore
   resolves its root via `importlib.resources.files(<pkg>)` and must not be zip-imported — wheels
   unpacked into `site-packages` (what pip/uv do) satisfy this; a zipapp or `--zip-safe` egg does
   not. Worth an explicit test, since the failure is a `TemplateNotFound` at run time rather than
   at import.

### farrier keeps no workflow knowledge

Decided (2026-07-29). A workflow that owns its own dependencies, its own prompts and its own entry
point has no reason to also be a thing the *installer* has an opinion about. `workflows:` leaves
`agents.yml`, and farrier goes back to what it is — the skills/prompts installer.

**The prompt-scanning half is already dead.** `Renderer.validate_workflow_dependencies` scans a
selected workflow's `prompts/*.md` for `instruction_ref(…)` / `prompt_ref(…)` and reports skills the
repo has not selected. It has **zero call sites**, and the feature doc says so
(`docs/features/farrier/concepts/renderer.md:167`: *"No current call site in `install.py` invokes
this — it is exposed for external tooling/tests"*). `_prepend_workflow_header` and
`_workflow_claude_md` in `farrier/workflows.py` are likewise uncalled — residue of the install path
that already went away. Deleting `extract_workflow_dependencies`, `validate_workflow_dependencies`,
both header helpers and the `renderer.py:29` import costs nothing that runs today.

**The launcher is the coupling that actually matters**, and it breaks under packaging rather than
merely going stale. `launcher.py` renders one compose service per selected workflow:

```yaml
source: ${AGENTS_DIR:-…}/workflows/{wf}    # AGENTS_DIR = `farrier config show library_dir`
target: /workflow
WORKFLOW_PATH: /workflow/workflow.yaml
{docker_sock_block if wf == "coder" else ""}
```

Three things wrong with that after the flip: the bind mounts a library subdirectory that a wheel
does not have, `WORKFLOW_PATH` names a `workflow.yaml` that no longer exists, and the last line is
farrier **branching on a specific workflow name** — the same violation class as
`scriptutil.build_dispatch_list`, in the installer this time. A workflow knows what its own
container needs; farrier cannot, and should not try.

So launcher/compose generation moves into the workflows package, and `make agent-run WF=coder`
becomes `workhorse run coder`, resolved through the entry point. The full deletion set in farrier:

| Site | Fate |
|---|---|
| `renderer.py:577` `validate_workflow_dependencies`, `workflows.py:85` `extract_workflow_dependencies` | deleted (uncalled) |
| `workflows.py:115,134` `_prepend_workflow_header`, `_workflow_claude_md` | deleted (uncalled) |
| `renderer.py:440-449` unknown-workflow-name validation | deleted with the selection key |
| `sources.py:140,167,175` the `workflows:` selection key | deleted |
| `launcher.py` `render_agents_mk` / `render_local_compose` per-workflow blocks | move to the package |
| `outputs.py:71,232-237` `.agents/workflows` cleanup + `--check` skip | keep one release as legacy cleanup, then delete |
| `workflows.py:24` `collect_template_values` | **survives** — reads `vars:`/`template:` from `agents.yml`; not workflow-specific, just misfiled |

**Landed and deferred (2026-07-29, while building).** The four uncalled rows are gone, and with
them `renderer.py`'s import and the `validate_workflow_dependencies` entry in
`docs/features/farrier/concepts/renderer.md`. The **launcher rows did not land, and cannot until
the first workflow is packaged**: they are one change, not two. `.agents/agents.mk`'s workflow
targets and the whole of `.agents/local.compose.yaml` are generated *from the selection list* —
delete the `workflows:` key and `make agent-run` / `make agent-native` / the compose services
vanish from every installed repo, while the only way to run any base-library workflow is still
exactly those targets (nothing is packaged yet; `workhorse run <name>` has an entry point to
resolve but no distribution registering one). That is the "cannot land without breaking the YAML
engine" case, so the launcher/compose move, the selection key and the unknown-name validation go
together with the ports. `outputs.py`'s legacy cleanup stays as the table already says.

**The one thing not to simply delete.** The pre-flight check is dead code, but the failure it was
built for is live and worse than it looks: of the ~32 distinct skill names the base workflow prompts
reference, only two (`stablemate-okf-modeling`, `stablemate-documentation`) exist in the base
library — `go` ×8, `go-testing` ×12, `story-docs` ×10, `flutter` ×7, `write-epics-and-stories` ×5,
`developer`, `code-review`, `pulumi`, `react-router` resolve only in an overlay. An unresolved
reference renders as the prose string `generated story-docs instruction file when installed`
directly into an agent prompt, silently. That validation belongs in **workhorse**, at render time or
under `--dry-run`, where the renderer already is — not deleted, and not back in farrier.

## The shape to build

*(Revised after the `author` rendering. The previous draft — module-level `@workflow.flow`
functions taking typed payload models — is kept in "Rejected along the way" with the evidence that
sank it.)*

### Registration and calling

```python
from workhorse.pyflow import Blueprint, Continue, Done, Await, Registry, Workflow, WorkflowFailed
from workhorse_workflows import kit

blueprint = Blueprint("coder")


@blueprint.node(retries=2, timeout=600)
def run_tests(logger, *, story: str) -> TestReport:
    ...                                             # side effects live HERE


class Coder(Workflow):
    story: str = ""                                 # an input: `workhorse run coder --param …`

    def setup(self) -> RunContext:                  # once, before the first state; then frozen
        return RunContext(**self.call(load_config).model_dump())

    def start(self) -> Continue | Done:
        self.agent("prompts/plan.md", returns=Plan, args={"story": self.story})
        return Continue(None, self.qa, story=self.story, attempt=0)

    def qa(self, story: str, attempt: int = 0) -> Continue | Done:
        for _ in range(3):                          # native control flow, inside the state
            report = self.call(run_tests, story=story)   # node → plain typed value
            if report.outcome == "valid":
                return Continue(report, self.record, story=story)
        return Continue(None, self.escalate, story=story)


workflow = Registry("coder").add_blueprints(kit.blueprint, blueprint)
main = workflow.main(Coder)                     # the callable, never a call at import
```

Decisions embedded above, each with its reason:

- **A workflow is a class; its methods are the states.** The previous draft made every state a
  module-level function, which forced a payload model per state, which made every state boundary a
  place the payload had to make sense — and that pressure fragmented the machine. The `author`
  rendering came out at **nine states for 159 nodes** once the models were gone. See below.
- **Nodes live in blueprints, not on the workflow.** A blueprint is a node library: free functions,
  `logger` first — the contract today's `scripts/*.py` already have via `main(logger)`, so they
  port with the argv/JSON envelope stripped and nothing else. `add_blueprints(...)` is plural
  because the point is composition: a workflow picks up `scriptutil`'s `await_operator`,
  `commit_all`, `push_branch` rather than re-implementing them a fourth time. This reverses
  "`workflow.logger` via `ContextVar`" — `Concatenate[Logger, P]` (below) strips the parameter for
  the type checker, so an explicit first argument costs nothing and keeps a node a plain function
  you can call from a test.
- **The registry is the composition root, and `registry.nodes` is what actually runs.** `self.call`
  is handed the *function object* because `Concatenate[Logger, P]` needs it to type the arguments —
  but the function is read for its registered **name**, and what runs is whatever the run's node
  index holds under that name. That makes `add_blueprints(...)` load-bearing rather than
  bookkeeping: a node whose blueprint the registry never folded in fails at the callsite naming
  `add_blueprints`, instead of running anyway because the stamp was on the function. Strictness is
  the point — the index is the one place a run's node implementations can be substituted, and a
  seam only holds if nothing can route around it.
- **Nodes return plain values; states return a transition.** Wrapping node results would put
  `.result[...]` at every callsite and re-erase the typing. States are different: their return value
  crosses a persistence boundary, is what gets checkpointed, and is the only place a
  terminate-vs-continue decision exists.
- **Three transition types, not one nullable field.** `Continue(result, next, **params)`,
  `Done(result)` and `Await(...)` make illegal states unrepresentable;
  `WorkflowState(result=..., next=None)` leaves "what does `result` mean while continuing?"
  undefined and unenforceable.
- **Failure stays an exception.** `raise WorkflowFailed(reason)` — it needs a traceback and has to
  compose with the retry ladder in `runner/agent.py`. An `Abort` variant would be a second path
  through the same machinery for no gain.
- **Transition payloads are keyword arguments, not typed models.** *(Reverses the previous draft.)*
  The next state's own signature is the schema; a model beside it duplicates that signature and
  then has to be kept in step with it. `ParamSpec` recovers everything the model was there for —
  see "What checks the arguments". `dict[str, Any]` does not come back: it survives in exactly one
  place, `self.agent(args={…})`, because a prompt genuinely has no signature to check against.
- **`self.call` / `self.agent` / `self.handoff` are seams, not conveniences.** Calling a node
  function directly would work and would be invisible. Going through `self.call` is what makes it a
  node: its own span, its own recorded `output.json` — which is what `self.output(…)` later reads —
  and, the payoff, a resolution through the run's node index, which is what makes both `--dry-run`
  and a test a **substitution** rather than a patch.

### The node index is the substitution seam

`RunEnv` carries the run's dependency set — its node index, its agent stand-ins, its agent runner —
because those are inputs to a run, not module globals. Everything downstream follows from that one
choice:

```python
env = RunEnv(..., nodes=research.workflow.override(clone_repo=fake_clone), run_agent=scripted)
drive(Research(topic="x"), env)
```

A test **supplies dependencies**; it does not reach into another module and assign over its
attributes. The before/after is the `research` suite, which used to do both kinds of patching:
`pyflow_engine.agent_runner.run_agent = agent` with a `finally` that put it back, and
`patch("…research.nodes.setup.allow_all_directories")`. The first is a global mutated for the
duration of a test — order-dependent and invisible to anything reading the workflow; the second
names a private symbol two packages away, so it breaks when that node is refactored even though the
behaviour under test did not change. Both become constructor arguments.

The rule is about *dependencies*, not about the word `patch`. Lowering `MAX_REWORKS` so a
test spends three loops instead of four replaces no seam — the cap is the workflow's own
constant and the guard still reads it — and wrapping `write_state_checkpoint` to collect
what it wrote is an observation, not a substitution. Those stay.

The same seam is what `--dry-run` uses, so there is one substitution mechanism rather than a test
mechanism and an engine `if`. See "`--dry-run`, and what happens to `dot`".

Two rules keep it honest:

- **A name the index does not carry is an error**, not a fallback to the stamped function. The
  index would otherwise be advisory — a node could be substituted or not depending on whether its
  blueprint had been registered, which is precisely the class of bug a seam exists to remove.
- **Nothing is resolved at import.** The index is read per call, from the env, so the same workflow
  module drives a real run, a dry run and a test without knowing which it is in.

### Where state lives

This is the part the rendering settled most sharply, and it is a rule, not a style: **if a state
writes it, it is a parameter of the next state.** Three tiers and no fourth.

| tier | written by | lifetime | checkpointed |
|---|---|---|---|
| inputs (class fields) | the operator, via `--param` | the whole run | once, at launch |
| `self.ctx` (frozen model) | `setup()`, exactly once | the whole run | once, after setup |
| state parameters | the state before it | one hop | every transition |

**The class carries no mutable state.** The consequence is that a checkpoint is a readable — and
hand-editable — line of JSON:

```json
{"state": "write_story", "params": {"epic": "auth", "story": "login-form", "resolves": 1}}
```

A parameter does not have to be a scalar. It may be a model, in which case the checkpoint stores
its JSON projection and the state's own annotation validates it back on the way in — the same
`TypeAdapter` pass that already puts `"docs/epics"` back into a `Path`. So this is equally a
checkpoint:

```json
{"state": "measure", "params": {"gate": "throughput", "budget": {"reworks": 2, "lead_reviews": 0, "extensions": 1}}}
```

That is not merely a smaller checkpoint. It is what makes a whole class of bug inexpressible. The
`author` YAML renders `{{ epic }}` into its commit message, where it resolves to whatever
`select_epic` last wrote into the run context — many nodes earlier, possibly several times over.
Under this rule the closing state has no `epic` in scope and never will, because nothing passed it
that far. A dependency that has to survive nine states has to be threaded through nine signatures,
and *being annoying to write is the point*: it prices the coupling instead of absorbing it.

Two things fall out, both visible in the rendering:

- **Derived values get derived, not carried.** `epic_dir`, `story_dir`, `story_path` and three
  context-file paths were fields on the first draft of the class. Every one is a pure function of
  `(ctx, epic, story)`, so they became four module functions and no state passes them anywhere.
- **Loop budgets become legible, and get billed.** A rework counter is an ordinary parameter, so
  "this run is on coverage rework 2 of 3" is in the checkpoint rather than inside a counter node's
  output. The bill is that a counter owned by an outer loop must be passed through the inner states
  that never read it — two of them, in `author`. Two is the honest price; if it were seven, that
  would be the design reporting that the loop is wrong. Past two counters the bill is paid once
  instead of per counter: they travel as **one frozen model** — `research`'s `Budget` — which a
  state bumps by returning a new instance rather than mutating a parameter. That keeps the
  threading cost at one name per signature while the checkpoint stays legible, one nested object
  instead of three loose integers.

`setup()` exists for the residue and is deliberately narrow. In `author` it holds two strings:
`base_branch` is decided at the top of the run and used only at the very bottom, and threading it
through seven uninterested states would be worse than the disease. It is not a place to stash
progress — states cannot write it.

#### The fourth thing, which is a read and not a tier

Threading every value through the transition is right for control — *which* story, *which* attempt —
and wrong for bulk. A survey manifest or an inventory has no business being copied into a checkpoint
that a human is supposed to read. Decided (2026-07-29): a state may read a previous node's recorded
output by reference.

```python
services = self.output(build_plan, "services")   # not: threaded through four transitions
services = self.output(build_plan).services      # the same read, typed — see below
```

This is not a fourth tier, and the distinction is the whole of why it is safe. A tier is somewhere
state is *written*; `self.output` writes nothing. It reads an artifact that `self.call(build_plan,
…)` already recorded and checkpointed — the durable `output.json` the seam exists to produce. The
run directory was always the real store; this only stops pretending the transition has to be the
only way back to it.

It is deliberately not the ambient bag returning. `{{ epic }}` in the YAML means *whatever last
wrote that key*; `self.output(build_plan, "services")` names its producer, so the read is greppable
in both directions and a missing producer is a startable error rather than an empty string. But it
is the one construct here that can recreate the coupling this design prices, so it wants one rule
now and one decision later:

- **The rule**: parameters carry what the *next* state branches on; `self.output` carries what a
  later state merely consumes. If a state branches on it, thread it.
- **The decision (open)**: which invocation a node name resolves to when the node ran more than
  once — in a re-entered loop state, or in a state that ran, crashed, and ran again. Last write is
  the obvious answer and is probably right; it is also exactly the ambiguity that made `{{ epic }}`
  a bug, so it needs stating rather than defaulting.

### What checks the arguments

Every seam takes `**kwargs`, and loose kwargs are exactly how the YAML's untyped `with:` bag would
sneak back in one layer up. `ParamSpec` closes it; the engine side is four signatures:

```python
def call(self, node: Callable[Concatenate[Logger, P], T],
         *a: P.args, **kw: P.kwargs) -> T: ...      # Concatenate strips the injected logger;
                                                    # -> T types the *result*, not just the call
def agent(self, prompt: str, *, returns: type[T], args: dict) -> T: ...
def handoff(self, wf: Callable[P, W], *a: P.args, **kw: P.kwargs) -> W: ...

class Continue(Generic[P]):
    def __init__(self, result: object, next: Callable[P, Transition], /,
                 *a: P.args, **kw: P.kwargs): ...
```

`handoff` gets it free: a `Workflow` subclass is a Pydantic model, so its synthesised `__init__` is
the signature being checked against.

`self.output` can be typed the same way, and should be, with one adjustment worth making now:
`self.output(build_plan) -> BuildPlan` reuses the node's declared return type, so the field access
after it is checked by the same machinery that checks `self.call`. The string-key form
`self.output(build_plan, "services")` cannot be — a `str` is opaque to a checker without `Literal`
overloads per node — and it re-introduces the stringly-typed access this design is trying to leave.
Return the model; let attribute access do what it is for.

**The transition target is positional** — `Continue(result, self.qa, story=…)`, never
`next=self.qa` — because `P.kwargs` has to own the whole keyword namespace. That is the right shape
independent of the typing: under a `next=` keyword, no state could ever have a parameter named
`next` or `result` without colliding with the constructor.

`ParamSpec` covers author time only, and these parameters cross a disk boundary. Three moments,
three mechanisms, all reading the same annotations:

| moment | mechanism | catches |
|---|---|---|
| author time | `ParamSpec` | wrong name, missing required parameter, wrong type |
| transition time | `inspect.signature(next).bind(**kw)` inside `Continue.__init__` | dynamically-built transitions, and anyone not running a checker — *before* the checkpoint is written rather than after the resume |
| resume time | `pydantic.validate_call`-style coercion against the signature | JSON off disk: `"docs/epics"` back into a `Path`; a hand-edited checkpoint naming a parameter the state does not have |

The third is the one that pairs with the hand-editable checkpoint: if the checkpoint is meant to be
edited, something has to validate the edit. Together they are the argument for annotating state
parameters even where every one of them is a `str`.

### Waiting is a transition, not a blocking call

`await-operator.py` is 280 lines of raw inotify over `ctypes` with a 300-second heartbeat, and
today it **blocks inside a node** until a human writes to a context file. The first rendering kept
that — `self.call(scriptutil.await_operator, …)` — because it made the operator gate an ordinary
helper callable from anywhere. Decided instead: a third transition type.

```python
return Await(context_path, questions, self.write_story,
             epic=epic, story=story, resolves=attempt + 1)
```

Read as *"checkpoint here; resume at this state with these parameters when that file changes."*
Two reasons, the first specific to this design:

1. **Blocking makes the wait the only run state that is not in the checkpoint.** Everything else
   became legible on disk; "blocked on a human at `docs/epics/auth/context.md`, story-split stage"
   would remain a stack frame, unreadable without asking the process. That is precisely why
   `await-operator.py` carries a best-effort push to groom's `/push/blocked` today — the backstop
   exists because the state is otherwise invisible. As a transition it is in the checkpoint, and
   the push becomes a projection of run state rather than a side-channel.
2. **A blocked run otherwise pins a process, a checkout and a branch** for as long as the human
   takes, which is days.

The 280 lines do not move — they are **deleted**. Decided (2026-07-29): the runtime waits by
**polling the file synchronously**, not with inotify. inotify is Linux-only, and a workflow runner
that cannot wait for a human on macOS is not portable; `ctypes` against a kernel API is also the
single most fragile thing in `scriptutil`, for a wait whose latency budget is *days*. A `stat` loop
on an interval is a dozen lines, works everywhere, and is indistinguishable at this timescale.
`check_feedback.py` — the *non*-blocking poll of the same file protocol — stays an ordinary node,
and the pair becomes coherent: both poll, one returns immediately and one keeps going.

The wait therefore blocks the driver in-process, and that is what ships. The `Await` transition
still earns its place: **the checkpoint is written before the wait begins**, so "blocked on a human
at `docs/epics/auth/context.md`" is on disk and readable by groom whether or not the process
survives. A suspend-and-exit arm can be added later behind the same transition without touching a
single workflow — which is the property the transition was for.

**The cost, stated plainly.** A suspension can only happen at a state boundary, because the
checkpoint is `(method, params)` and resuming into the middle of a Python function would mean
making states generators. So an `Await` cannot be buried in a helper called from inside a loop: it
must be *returned*, and every caller has to propagate it. In `author` that splits the two states
whose `while blocked: … retry` loops call the operator gate. Fat states are free right up until
you need to suspend inside one, and this is where that bill arrives.

**What it costs, given coarse resume.** Resume re-enters a state from the top and there is no
intra-state memo (decided below), so **everything the resume target does before it reads the answer
runs again, for real** — including agent calls. That is not a footnote; it is a design rule:

> An `Await`'s resume target must be a state whose prefix is cheap. The natural shape is a state
> that exists *only* to consume the answer, entered with the answer's parameters and reading
> whatever else it needs by reference.

`self.output(...)` is what makes that affordable — the consuming state does not re-derive the
expensive values, it names the node that already produced them. The two decisions are one design:
coarse resume is only tolerable because a state can read the previous state's recorded outputs
without re-running them.

Blocking in-process sidesteps the whole question for the ordinary case, since nothing re-enters at
all. The rule matters for the crash that happens *while* blocked, which over a multi-day wait is not
a rare case.

### The driver

```python
def drive(wf, state="start", params=None):
    params = params or {}
    for _ in range(wf.max_transitions):              # the gas tank already bounds this
        with writer.subscope(state):
            outcome = run_state(wf, state, params)   # validates params against the signature
        if isinstance(outcome, Done):
            return outcome.result
        if isinstance(outcome, Await):
            checkpoint(state=outcome.state, params=outcome.params, waiting_on=outcome.path)
            poll_until_touched(outcome.path)         # portable stat loop; see above
        else:
            checkpoint(state=outcome.state, params=outcome.params)
        state, params = outcome.state, outcome.params
    raise WorkflowFailed("transition budget exhausted")
```

`Await` and `Continue` differ in exactly one line, which is the point: the transition is recorded
identically, and the wait is something the driver does between recording it and stepping. Adding a
suspend-and-exit arm later means returning instead of falling through — no change above this
function or below it.

This is `_step_loop` with a coarser node. `_run_flow` (`main.py:707`) and `writer.subscope` port
over largely intact.

## Resume

The checkpoint is `(method name, params)` — a state name and a flat dict of JSON-serialisable
arguments, nothing more. A resume re-enters **exactly one state**. There is no growing replay
prefix, which is what makes this design affordable at the runs workhorse targets (the stated goal
is a single run surviving a week).

**Resume is coarse, and there is no intra-state memo.** Decided (2026-07-29), reversing the earlier
recommendation of "fine within a state, coarse across". Resuming is *calling that state again with
those parameters* — nothing inspects what the previous attempt got through. Consequences, all of
them wanted:

- **No step keys and no callsite fingerprinting.** The `(scope path, callsite fingerprint, ordinal)`
  scheme, and the "is this the same callsite" question it existed to answer, are simply not built.
  That question has no good answer — a fingerprint is a guess about whether edited code is still the
  same code — and the design is better off never asking it.
- **A resume is a plain function call**, so a state can be tested by calling it, and the checkpoint
  file is the whole of the resume state. There is no second, invisible cache that can disagree with
  it.
- **State size is the unit of work lost**, which finally gives authors a concrete reason to pick a
  granularity — today nothing pushes on that. It also makes fatness stop being free: a state is as
  expensive to re-enter as its prefix, which is the pressure that puts an `Await`'s resume target on
  a diet.

What pays for the re-run is `self.output(node, "value")`: a re-entered state recovers a previous
state's expensive results by naming them rather than by recomputing them. Coarse resume plus
addressable outputs is one decision, and neither half is sound alone.

**`self.output(node, …)` resolves to the latest invocation, exactly as today.** Decided
(2026-07-29). This is less a choice than a reading of the artifact layout: `ArtifactWriter.write_step`
does `step_dir = self.run_dir / node_id`, `mkdir(exist_ok=True)`, then `write_text` — a plain
overwrite. A node that runs three times in a rework loop leaves **one** `output.json`, the last one,
and `templates.py:get_node_output` already reads that same path. There is no earlier invocation to
resolve to; the previous ones were destroyed when they were superseded. Four notes:

- **Node dirs are flow-scoped**, so this is narrower than it sounds. A sub-flow writes under
  `<run>/<node_id>/_flow/…`, so the same node invoked from two different flows does not collide.
  Only *re-entry of the same node within the same flow* overwrites.
- **The history is not lost, it is just elsewhere.** `events.jsonl` is append-only and records every
  `enter`/`done`, so a run's full invocation sequence stays auditable. If a workflow ever genuinely
  needs a *prior* invocation's output, that is a new artifact layout (per-invocation subdirectories),
  not a change to how the lookup resolves — and nothing in `author`'s nine states wants it.
- **This is not the `{{ epic }}` ambiguity**, despite the resemblance. That bug was a shared context
  key with an unnamed producer: the reader could not tell *who* wrote it. `self.output(build_plan,
  "services")` names its producer in the call. What stays unnamed is only *which invocation*, and
  within a loop those are the same node doing the same job — the last one is the one that counts.
- **The sharp edge is the missing file, not the stale one.** `get_node_output` returns its `default`
  (`""`) when the node has not run, when the run dir is unset, and when the JSON fails to parse —
  three different failures, all silent, all indistinguishable from a legitimately empty value. The
  new `self.output()` should **raise** on a node that has not run in this run rather than inherit
  that. It is the same silent-empty-string class as an unresolved `instruction_ref`, and the same
  argument applies.

### The rules resume imposes

1. **State bodies must be idempotent, not merely deterministic.** Coarse resume replaces the weaker
   replay-determinism rule with a stronger one: a state may run twice, in full, against a world its
   first attempt already changed. `for _ in range(3)` is fine. A node that appends to a file, opens
   a PR, or pushes a branch has to tolerate finding its own previous work — which is why
   `find_open_pr` exists beside `open_pr` today, and that pattern becomes the norm rather than a
   nicety. This is the real price of dropping the memo, and it is paid in nodes, where it is
   visible, rather than in an engine cache, where it is not.
2. **State parameters must serialize, and should stay small.** They *are* the checkpoint. No live
   objects across a boundary — no `Repo`, no `Ostler` handle, no open file. Size is not a hard
   limit: a parameter may be as large as it genuinely needs to be. But the checkpoint is meant to be
   read and hand-edited by a human at hour 30 of a stuck run, and a state that wants a previous
   node's whole result should reach for `self.output(node, "value")` instead of copying it into the
   transition. `author`'s parameters are `str`, `int` and `Path`; that is the target, not an
   enforced ceiling.
3. **Nothing may be stashed on `self`, and the base class enforces it.** Decided (2026-07-29): the
   instance is **frozen after `setup()` returns**. A mutable field is a parameter that skipped the
   checkpoint — it survives a transition in memory and does not survive a resume, so the bug appears
   only after a crash or an `Await`, which is the worst time to find it. Documentation would not
   have held: the violation is one `self.x = …` away and looks like ordinary Python. Freezing costs
   the escape hatch, and the escape hatch is the thing being ruled out. `setup()`'s frozen
   `self.ctx` is the sole run-scoped field and is written before the first state runs.
4. **Identity is the plain name, and a rename declares an alias.** Decided (2026-07-29), and it
   reverses the earlier suggestion of pinning every name with an explicit identifier. Pinning taxes
   all states forever to protect against a rare event; `aliases=[…]` charges only the name that
   actually changed:

   ```python
   @workflow.state(aliases=["qa_gate"])       # was qa_gate before 0.9
   def qa(self, story: str, attempt: int = 0) -> Continue | Done: ...

   @blueprint.node(aliases=["run_pytest"])
   def run_tests(logger, *, story: str) -> TestReport: ...
   ```

   The pairing with the hard-failure rule is what makes this complete, and neither half works alone.
   A resume that finds a name matching no state and no alias **fails loudly** — never a cache miss,
   never a silent fresh start — so an undeclared rename is detected; the alias is then the one-line
   fix. Aliases do not prevent the mistake, they make it cheap once the mistake announces itself.

   **Nodes need this as much as states**, which is not obvious until you notice what else became
   data on disk: `self.output(node, …)` resolves by node name against the run directory, so renaming
   a node breaks output lookups in exactly the way renaming a state breaks checkpoints. One rule
   covers both, and the rule generalises: *any name that reaches disk needs an alias mechanism.*

   Two obligations that come with it:

   - **The alias namespace is shared with the live names, and collisions are a startup failure.**
     An alias that shadows a live state, or that two states both claim, would silently route a
     resume to the wrong place — the one new failure mode aliases introduce. Build the map at
     registration and raise there, where it costs a test rather than a run.
   - **Aliases retire.** They only need to outlive the longest run that could still resume, and the
     stated target is a week. Tie removal to releases rather than to taste, or the list becomes a
     changelog nobody prunes. `dot` and `--dry-run` render live names only.

## `--dry-run`, and what happens to `dot`

A dry run is **the node index with every entry replaced by its stand-in** — not a branch inside
`Engine.call`. That is the whole mechanism: `--dry-run` builds a substituted index off
`registry.nodes` and hands it to the run, so it exercises exactly the resolution path a real run
uses instead of a second path that only exists in dry-run mode.

What a stand-in is, in order of preference:

- what the node declared, `@blueprint.node(stub=lambda …: TestReport(outcome="valid"))` — the
  author's answer to "what would this have returned";
- otherwise a blank instance of the node's return model. It type-checks and it is honest about
  knowing nothing.

Agent turns get the same treatment: `Registry.stub_agents({"check-gate": …})` keys a canned reply
by prompt stem, and a prompt with no entry falls back to a blank model. Stems, not paths, because
the stem is what the workflow author actually names.

The distinction that matters is **what a fail terminal means**. With blank stand-ins, every branch
reads a blank field and takes an arbitrary path, so a workflow that ends in `WorkflowFailed` has
reported nothing about itself — which is why `run.py` reports such a run as a fail terminal rather
than failing on it. Once a registry declares stand-ins, that exemption lifts: the stand-ins are the
author's claim about which path is the success path, and a dry run that still fails has found a
real defect. So the exemption is conditional on the registry declaring nothing, and a workflow
earns a stricter smoke test by describing its own happy path.

Two distinct payoffs, of unequal value:

**A CI smoke test (the real payoff).** Run the whole workflow with nodes stubbed: every prompt path
resolves, every state name binds, no import errors, no unreachable state. This catches the failure
mode that actually costs — a typo discovered at hour 30 of an unattended run. Note that `ParamSpec`
has since taken the argument-checking half of this job and moved it earlier, to the editor: what
dry-run is left holding is everything a type checker cannot see, which is the filesystem
(prompts) and reachability.

**A state-granularity graph (secondary, approximate).** To find a state's out-edges you enumerate
paths **within that state only**; you never explore cross-state combinations, because the
transition is data the driver reads. Cost is `sum over states of 2^(branches in that state)` rather
than `2^(all branches)` — linear in states, and branches-per-state is small by construction. The
rendered machine is an over-approximation (a state may be shown returning `escalate` on a path that
cannot actually occur), but unlike a declared `next=[...]` list it is derived from the code and
cannot drift from it.

Fat states make this weaker than it looked in the first draft: `author`'s nine states hide a lot of
interior. That is the trade the trilemma below already prices, and the counter-pressure is real —
`--dry-run` renders less the fatter a state gets, which is one of the few forces pushing the other
way.

This is the design's main non-obvious win, and it was not available in the flat-imperative variant.

## The trilemma this resolves

The same constraint surfaced three times in different clothes, so it is worth stating outright:
**native control flow, a complete static graph, and one source of truth — pick two.**

| Shape | Native control flow | Static graph | Single source |
|---|:-:|:-:|:-:|
| YAML today / `with`-block builder DSL | ✗ | ✓ | ✓ |
| Decorator `next=[...]` declarations | ✓ | ✓ | ✗ (drifts) |
| Flat imperative + replay | ✓ | ✗ | ✓ |
| **State machine of methods (this)** | ✓ *(inside a state)* | ~ *(between states)* | ✓ |

Splitting at the state boundary is what buys the partial third. It is not a full static graph — the
interior of a state is opaque — but the interior of a state is also the part nobody wanted to read
as a diagram.

## Packaging and distribution

Decided (2026-07-29). **One distribution, `workhorse-workflows`, published separately from
workhorse and living in this repo as a uv workspace member.** Not one distribution per workflow,
and not bundled into `workhorse-agent`.

### Not bundled into workhorse

The strongest evidence is already on disk. **No engine module imports `scriptutil`** — every
reference to it under `workhorse/workhorse/` is a comment or an error string. Meanwhile **67 files
under `base-library/workflows/` import it.** `scriptutil.py` (~1,000 lines) is a workflow-support
library that happens to live inside the engine's package, and it is why `gitpython` and `PyGithub`
are *required* dependencies of `workhorse-agent`: every `pip install workhorse-agent` pulls a
GitHub client into an engine that never talks to GitHub.

That is the bundling failure mode in miniature. Put the workflows in workhorse's distribution and
its dependency set becomes the union of every workflow's — `ostler` joins next, and the dependency
isolation that motivates this whole design is gone before it ships.

The second reason is the workflow-agnostic rule in `workhorse/CLAUDE.md`: *never bake one
workflow's vocabulary into the engine — no `plan-context` field names (`services[].type`,
`touched_layers`, layer→platform maps)*. `scriptutil.build_dispatch_list` reads
`plan_ctx["services"][].type`, `implementation_order`, `template.backend_layer_name` and
`template.mobile_layer_name`. The rule is stated and violated in the same repository. What holds
the line everywhere else is that workflows are *a different directory the engine cannot import*; a
shared wheel removes the last friction on that shortcut.

Two lesser reasons: a prompt edit must not ship an engine version (`make publish` already chains
core → workhorse → farrier, and coupling four workflows into it means every release moves
everything), and a third party publishing `acme-workflows` should use the same resolution
mechanism the base four use, not a story bolted on beside a privileged bundle.

The honest counter is API coupling: workflows import `Continue`/`Done`/`@workflow.node`, a hard
version edge to the driver. That argues for **one repo** — so a driver change and its ports land in
one commit and CI tests them together — not for one distribution. A version range expresses that
edge exactly; a shared wheel over-expresses it.

### Not one distribution per workflow

What the four actually need:

| Workflow | Python deps | On `PATH` |
|---|---|---|
| research | `workhorse-agent` | `uv` |
| author | `workhorse-agent`, `ostler` | — |
| coder | `workhorse-agent`, `ostler` | `make` |
| okf-builder | `workhorse-agent`, `ostler[vet]` | — |

Three of four are identical, and the one genuinely heavy dependency — playwright — is already
factored a level down as `ostler`'s `vet`/`qa` extras, so it is not a workflow-layer concern at
all. Splitting buys exactly one thing: a research-only user skips a small pure-Python package.

Against that, splitting costs three real things here:

- **`kit` stops being free.** As a module inside one distribution, shared plumbing is an import. As
  a fifth distribution it needs its own version, a range pin in four consumers, and four releases
  for every change — and shared plumbing is precisely where the churn is (the worklist primitive
  landed in 44e5060 and three workflows want it; `load-config`, `await-operator`, `check_feedback`,
  `init_counter` and `incr_counter` are already duplicated across workflow `scripts/` directories).
- **They release in lockstep anyway.** All four bind to the same driver API, so a driver change
  breaks all four at once. Four version numbers that only ever move together are four times the
  ceremony for zero independent motion.
- **They already reference each other.** author produces stories, coder consumes them, okf-builder
  feeds both. Shared `Story`/`Epic` models across four distributions is a dependency graph
  maintained by hand.

The dependency-isolation argument that motivates the flip is workflow-vs-**workhorse** — the
`pipx inject workhorse-agent ostler` problem — and one distribution with `ostler` in
`[project.dependencies]` resolves it completely. It was never workflow-vs-workflow.

### The mechanism stays plural

One entry point **per workflow**, not per distribution:

```toml
[project]
name = "workhorse-workflows"
dependencies = ["workhorse-agent>=0.8,<1", "ostler>=0.1"]

[project.optional-dependencies]
visual = ["ostler[vet]"]           # okf-builder's screenshot/crop path; coder's QA

[project.entry-points."workhorse.workflows"]
research    = "workhorse_workflows.research.workflow:workflow"
author      = "workhorse_workflows.author.workflow:workflow"
coder       = "workhorse_workflows.coder.workflow:workflow"
okf-builder = "workhorse_workflows.okf_builder.workflow:workflow"

[project.scripts]
workhorse-research    = "workhorse_workflows.research.workflow:main"
workhorse-author      = "workhorse_workflows.author.workflow:main"
workhorse-coder       = "workhorse_workflows.coder.workflow:main"
workhorse-okf-builder = "workhorse_workflows.okf_builder.workflow:main"
```

This is the part that matters for the future. `workhorse run coder` resolves through the same
lookup whether the workflow came from `workhorse-workflows`, a private overlay's own package, or a
third party's — the base four become the first four consumers of a general mechanism rather than a
special case. It is also what makes the single-distribution choice reversible: splitting later
changes which wheel provides an entry point, not how anything is found.

If per-workflow dependencies genuinely diverge later, extras (`workhorse-workflows[coder]`) recover
most of the isolation at a fraction of the release surface.

**`requires:` has no successor, and that is the point.** Decided (2026-07-29): there is no
`Blueprint(requires=[...])`. The YAML block was a hand-rolled dependency manifest that existed only
because a workflow was data with no other way to say what it needed; a distribution has
`[project.dependencies]`, and a second manifest that can disagree with the first is worse than
none — it can be satisfied while the install is broken, or fail while it is fine. If the
`ModuleNotFoundError` a missing dependency produces reads badly, the fix is a better message at the
import, not a manifest to maintain.

The name ties to the engine because that is the coupling that is real, and it tells a third party
what their package must target. It does not re-blur the boundary argued for above — `pytest-xdist`
does not imply pytest owns it.

### Each workflow gets a console script

The `[project.scripts]` table above is the second half of the same registration, and it is not
decoration. A workflow is an installed distribution now, so it can have a command; the only reason
`workhorse run <name>` was the sole front door is that a YAML file cannot be one.

```python
workflow = Workflow()
workflow.add_blueprints(kit.blueprint, nodes.blueprint)
workflow.add_flows(Surveyor, ParitySurveyor)     # so the CLI can name them
main = workflow.main(Author)                     # returns the console-script callable

if __name__ == "__main__":
    raise SystemExit(main())
```

`workflow.main(Author)` **returns** the callable rather than running — a module-level call cannot be
a `[project.scripts]` target, since the script's job is to be called after import, not during it.
The `workhorse.workflows` group keeps pointing at the `workflow` object, because discovery needs the
registry, not the entry function.

**Two front doors, one parser.** These are the same code path with the workflow name bound
differently:

```bash
workhorse run coder  qa --run-id=test123 --params '{"story": "AUTH-12"}'
workhorse-coder run  qa --run-id=test123 --params '{"story": "AUTH-12"}'
```

There is no second implementation to drift: `workhorse run <name>` resolves the entry point and
calls the same parser the script calls, with the name already supplied. That is the condition for
having two commands at all — the moment the script grows a flag `workhorse run` does not have, this
subsection is wrong.

**The positional after `run` is a flow**, exactly as it is today, and under this design it stops
being an engine feature. A flow is a `Workflow` subclass, so `run qa` is `drive(QA(**params))` — the
same class, driver and checkpoint file as when a state reaches it through `self.handoff(QA, ...)`.
`add_flows` exists only to map the CLI token onto the class — the caller never names a registry,
because `handoff` already holds the class and the class carries its registration. That is what lets
a sub-flow from another distribution bring its own prompt root and node index along with it; see
"A sub-flow is independent".

**`--params` binds to the entry class's model**, not to a context bag: `Author` for `run`, `QA` for
`run qa`. That makes the CLI the fourth front door onto the one validation this design already has,
and the only one an operator touches directly.

| door | what validates |
|---|---|
| transition | `Continue.__init__` binds against the target state's signature |
| resume | the checkpoint's params are coerced against that same signature |
| handoff | the sub-workflow's own model validates its args |
| **the CLI** | the entry class's model validates `--params` |

Worth stating in operator terms, because it is the visible win: `--params mode=stroy` becomes a
parse error naming the legal values, where today the typo reaches the mode branch, matches no case,
takes `default:`, and runs a mode nobody asked for. `--params epics_dir=docs/epics` arrives as a
`Path` because the field is annotated `Path`, not because a node remembered to convert it. The typed
target is also why bare `k=v` pairs can be accepted beside inline JSON — quoting stays load-bearing
only for nested values.

`--run-id` keeps its current meaning exactly: it names the stable run dir and defaults to a digest
of `--params`. It is the identity half of resume, and this design changes only what a checkpoint
*contains*.

Two smaller decisions:

- **Commands are prefixed** (`workhorse-author`, not `author`). These land on a user's `PATH`;
  `author` and `coder` are words other tools have a claim on, and the prefix also says which engine
  the command belongs to when it appears in a shell history a year from now.
- **A third party's workflow gets the same two doors for free.** It declares its own script and its
  own `workhorse.workflows` entry point; nothing here is reserved to the base four.

### Repo layout

```
stablemate/
  core/  workhorse/  farrier/  ostler/  groom/  saddlebag/
  workflows/                      -> workhorse-workflows (one distribution)
    src/workhorse_workflows/
      kit/                        # shared plumbing — a module, not a fifth distribution
      research/  author/  coder/  okf_builder/    # one package each — see below
  base-library/                   # library/skills + scaffolds only
```

Three distinct things "part of the stablemate project" could mean, and they resolve differently:

- **In the repo** — yes. Ports land in the same commit as the driver change they track.
- **In `[tool.uv.workspace] members`** — yes, and it needs no extra plumbing: `make sync` runs
  `uv sync --all-packages`, so membership alone puts it editable in the dev venv.
- **A dependency of the root `stablemate` project** — no. The root declares `[project]` with no
  `[build-system]`, is never published, and carries no runtime dependencies. It stays a pure
  anchor; `workhorse-workflows` publishes on its own.

`make build`/`publish` gain a target, ordered core → workhorse → workflows, for the reason the
existing Makefile comment already gives for core going first: publishing against an unpublished
dependency produces installs that cannot resolve.

### One workflow, several files

A workflow is a **package**, not a module. The single-file artifact under
[`author-workflow-python/`](author-workflow-python/) is a design convenience and is already at the
edge of one: 1,459 lines, of which `class Author` starts at line 900. **Nearly two thirds of the
file is node bodies the reader of the state machine never needs to see** — and that ratio only
grows, because nodes are where the work accretes.

```
author/
  __init__.py
  workflow.py            # the Workflow subclass, and nothing else
  schemas.py             # agent-reply schemas + node return types  (→ schemas/ when it grows)
  paths.py               # pure derivations: epic_dir, story_dir, story_path
  nodes/
    __init__.py          # assembles the Blueprint; the one import workflow.py needs
    config.py            # load_config, branch_author, …
    stories.py           # seed_story, select_story, validate_story, …
    coverage.py          # validate_epic_coverage, verify_surface_coverage, …
  flows/
    surveyor.py          # its own Workflow subclass, reached by self.handoff(...)
    parity_surveyor.py
  prompts/               # unchanged — see "Prompt rendering is workhorse's"

workflows/tests/author/  # outside the wheel — see "Where the tests go"
```

Each directory earns its place against something that exists today:

- **`workflow.py` is the file you read to see the graph**, and the whole readability argument for
  leaving YAML dies if it is also the file where 24 node bodies live. It keeps the name it replaces:
  `author/workflow.yaml` becomes `author/workflow.py`, so every path, habit and "where is this
  defined" answer survives the port, and a diff across the migration lines up by name. It is
  2,389 lines today and should come out at roughly a fifth of that. A reviewer of a state-machine
  change should not be scrolling past `subprocess` calls to find it.
- **`nodes/` is today's `scripts/`, renamed, and it is a directory even when it holds three
  functions.** `author/scripts/` is 48 files already (23 plus 25 under `surveyor/`); they port
  one-for-one into node modules with the argv/JSON envelope stripped and nothing else changed. The
  port stays a move, not a redesign, precisely *because* the directory survives. Group by subject
  rather than one file per node — `stories.py` holding four related nodes reads better than four
  files.
- **`flows/` is the YAML's `flows:` key.** Each file is its own `Workflow` subclass with its own
  states, reached by `self.handoff(...)`, and it is the reason `handoff` was un-rejected.
  `author/surveyor/` is already a sibling directory on disk (23 nodes; `parity-surveyor` is 8), so
  this layout makes explicit what the YAML expressed by nesting.
- **`schemas.py`** exists because agent-reply schemas and node return types are shared between the
  nodes that return them and the states that read them; putting them in either place makes the other
  import it. *(It was `models.py` in the previous draft. Renamed while porting `research` — `5d3f89d`
  — because "models" invited the rejected reading that these are payloads crossing a transition. The
  name now carries the decision; see "Rejected along the way".)*
- **`paths.py`** is where "derived values get derived, not carried" lands as a file. The three-tier
  rule sends `epic_dir`/`story_dir`/`story_path` out of the state machine as pure functions of
  `(ctx, epic, story)`; they are imported by both states and nodes, so they cannot live in either.
  Small workflows will not have this file. `author` has four such functions and `coder` more.

**One rule, and it is checkable: imports point one way.** `workflow.py` imports `nodes/`, `flows/`,
`schemas` and `paths`; nothing under `nodes/` imports `workflow.py`. That is what keeps a node a
plain function a test can call with a logger and no engine, and what stops the state machine's
vocabulary leaking into the reusable layer — the same failure `scriptutil.build_dispatch_list` is an
example of two sections up. Worth enforcing with an import rule rather than a convention, since the
violation is one convenient import away and invisible afterwards.

Two consequences to settle when building:

- **The entry point names the module, not the package**: `author =
  "workhorse_workflows.author.workflow:workflow"`, and the console script names `…workflow:main` in
  the same module. The stutter is the price of keeping the filename; it is the ordinary shape
  (`app.app`, `celery.celery`) and it buys an unambiguous target. The alternative — re-exporting
  `workflow` from `__init__.py` — means importing the package for any reason executes the
  state-machine module.
- **`add_blueprints` is where the assembly shows.** `nodes/__init__.py` builds one `Blueprint` from
  its submodules so `workflow.py` reads `workflow.add_blueprints(kit.blueprint, nodes.blueprint)`.
  If that file ever grows logic beyond registration, the split has been drawn in the wrong place.

#### How small, and what to do when a file is not

Decided (2026-07-29), because the shape above is only load-bearing if it is normative. The layout is
not a suggestion a port may flatten, and it is not a judgement call to re-argue per workflow — a
port that decides its own layout is a port that decides it by line count as it goes, which is how
`research` ended up with the shape the next section corrects.

Three rules, in order of how often they bite:

1. **One subject per module, and the docstring is the test.** A module whose one-line summary needs
   an "and also" is two modules. This is the rule that actually does the work; the number below only
   tells you when to apply it.
2. **~400 lines is a trigger to look, not a lint.** Past it, ask rule 1. Prose is not the enemy —
   `research/workflow.py` is 617 lines and mostly docstring, and splitting *that* would trade a file
   you can read top to bottom for two you cannot. `subprocess` bodies at 400 lines are a different
   answer than commentary at 600.
3. **Every part that grows is a directory before it needs to be**, and the same names mirror across
   them: `nodes/stories.py` ↔ `schemas/stories.py` ↔ `tests/author/test_stories.py`. Splitting a
   flat module later renames every import in the tree; starting as a package costs one
   `__init__.py`.

**`schemas.py` becomes `schemas/` on the same trigger**, mirroring the node module names, with
`schemas/__init__.py` re-exporting the classes so `from ..schemas import GateCheck` keeps working.
Plain re-export is right here and it is *not* the `kit.__getattr__` case in the ledger: that
forwarding exists to preserve a monkeypatch seam on module attributes, and a model class is neither
patched nor re-read per node run.

**`workflow.py` holds exactly one class, and there are no state mixins.** When it is still too long
after the node bodies are gone, the levers are, in order: derivations to `paths.py`, shared
constants to `constants.py` (only once nodes read them too), and a genuine sub-graph to `flows/`.
What is *not* a lever is splitting states across files. States are methods of one frozen Pydantic
class whose names are registry keys and alias targets; a mixin scatters the machine across files
while leaving it one class, so the graph stops being readable in one place without becoming readable
anywhere else. And `flows/` is not a general splitting tool either — `handoff` means *run this to its
own `Done` and return the result*, so extracting states that merely happen to be adjacent invents a
sub-workflow that has no terminal of its own. A 1,200-line `coder/workflow.py` with 71 nodes
elsewhere is the machine being genuinely large, and it stays one file.

#### Where the tests go

**`workflows/tests/<workflow>/`, outside `src/` and outside the wheel** — decided (2026-07-29),
correcting the `tests/` line the layout sketch above used to carry inside the package. The shipped
`research` port already does this (`workflows/tests/test_research_workflow.py`), and it is right for
the ordinary src-layout reason: tests are not part of the distribution, and a `src/` package that
ships them makes every install carry them.

What changes is the granularity. One file per workflow is already 404 lines for the *smallest* of
the four; `coder`'s 71 nodes cannot land in one. Mirror the node modules — `tests/coder/test_stories.py`
beside `nodes/stories.py` — plus one module for the machine itself (`test_workflow.py`: the
end-to-end run, the resume, the dry-run). The pattern inside each file does not change and is
`test_research_workflow.py`'s: real nodes against a temp git repo with only the agent turn scripted.

#### What the `research` port shipped, and why it is not the template

`research` landed flat — `nodes.py` (316), `schemas.py` (236), `workflow.py` (617), one 404-line test
file — and for 3 nodes that was the right size to stop at. It is the wrong thing for the next three
ports to copy, and they will copy it, because a worked example outranks a design section every time:
`author` has 48 scripts totalling 5,695 lines and `coder` has 71 totalling 8,661. A single `nodes.py`
at that scale is `scriptutil.py` again, and this design's whole packaging argument is that
`scriptutil.py` was a thousand-line module nobody meant to write.

So **`research` was restructured into the layout above before `author` is ported**, not after. It
was the cheapest moment — no behavior touched, one commit — and the only moment where doing it cost
one port rather than four. `nodes/` is now `setup.py` (73), `program.py` (200), `publish.py` (55)
over a 13-line `_blueprint.py`, with `schemas.py` at 236 and the tests mirroring the node modules.

That left `workflow.py`, and it left it at 617 lines of which the surplus was **parameter
threading, not logic**. The size pass took it to **517** with four levers, all of them private
helpers rather than a split — the file stays one class with no state mixins, per *One workflow,
several files*:

- **three counters became one `Budget` model** (`schemas.py`, now 284), threaded as a single
  parameter and bumped by returning a new instance. This is the case that made a model-valued
  parameter worth supporting;
- **`_program_args(**extra)`** for the `repo_dir` / `program_dir` / `progress_path` triple that
  appeared on 53 lines;
- **`_publish()`** for five identical `self.call(publish_results, …)` blocks;
- **`_record(gate_id, *, forced)`** for four `record-result.md` agent turns.

Two states did **not** take `_program_args`: `check_gate` and `rework` render prompts that take no
`progress_path`, and the reason is the point of the gate — the reviewer must not be anchored on
what the implementer wrote to the progress file. They keep literal argument dicts with a comment
saying so. A helper that quietly widened their argument set would have changed the experiment.

The pass also cost the engine a fix, which is the honest part of the result. `graph.py` read only
a state's own body, so moving an `agent(...)` into `_record` dropped the prompt from `dot` **and**
from `preflight`'s prompt-exists check — factoring silently bought less static coverage. The
reader now follows `self._helper(...)` into the class's own private methods and attributes what it
finds to the calling state (with a `seen` guard, since helpers may call each other). The rule the
design already had — a leading underscore is not a state — now costs nothing to use.

Worth keeping, because it is the clearest evidence the design does what it claims: the port's own
account of what the counters cost in YAML. The workflow needed six scripts and nine nodes to hold
three integers —

```
init_lead_counter  init_extend_counter  reset_rework     (three "set it to 0" nodes)
guard_rework       guard_lead_review    guard_extend     (three ">= literal" branches)
incr_rework        incr_lead_review     incr_extend      (three "+1" script nodes)
```

— and the caps could not be written in the branches, because a branch condition is a literal, so
`vars.max_reworks: "3"` was kept in step with `guard_rework`'s `"3"` **by a comment asking the next
editor to remember**. In Python the caps are module constants the guards read, a reset is a default
argument, an increment is `+ 1`, and a guard is `if`. Branch nodes went the same way: `route_gate`,
`check_killed_pre`, `decide_gate`, `route_lead_verdict` and `route_goal_verdict` are `if`/`elif`
inside the state that produced the value they branch on. **30 YAML nodes became 12 states**, and
the counters ended up in the checkpoint where an operator can read and edit them.

What did *not* collapse is the four terminals, because the difference between them is real: a goal
verdict (`reached` / `impossible`) is a scientific conclusion and ends the run clean, `Done(...)`;
a budget exhausted without a verdict is an apparatus failure and ends it red,
`raise WorkflowFailed(...)` — the old `program_dead` node.

### The `scriptutil` split (a deliverable, not a side effect)

This is what makes "ship separately" load-bearing rather than tidy. `workflows/…/kit/` absorbs the
domain half of `workhorse/scriptutil.py` — `github_client`, `resolve_github_token`, `find_open_pr`,
`push_branch`, `sync_to_origin`, `build_dispatch_list`, `get_affected_repos`, `resolve_workspace`,
`checkout_workspace` — leaving workhorse the engine-side seams the test harness patches
(`run_tool`, `fresh_import`, `find_repo_root`, `load_json`, `die`).

Measurable result: **`workhorse-agent` drops `gitpython` and `PyGithub` from its required
dependencies.**

**The pure-git helpers go to `kit` too — all of them — and workhorse keeps none.** Decided
(2026-07-29). The earlier draft left this as the one undecided cut, on the theory that git is
generic infrastructure a runner might plausibly want. The tree says otherwise: **`scriptutil.py` is
the only module under `workhorse/workhorse/` that imports `git` at all**, and no engine module
calls a single one of `open_repo`, `checkout`, `commit_all`, `clone`, `fetch_reset`,
`current_branch`, `rename_branch` or `default_branch`. "Generic infrastructure" that nothing in the
engine uses is just a workflow's library sitting in the wrong package. A clean cut also makes the
acceptance test binary rather than a judgement call: `git` does not appear in workhorse's imports.

`find_repo_root` stays, and is not an exception — it walks parent directories looking for
`agents.yml` or a `.git` **path**, and never touches GitPython. Testing a directory for existence is
not a git dependency.

Two things this move should collect on the way past:

- `open_repo` carries a lazy `from git import Repo` whose comment explains itself: importing
  GitPython runs a `git --version` probe, so the *many git-free scripts must be able to import this
  module* without a real git on `PATH`. Splitting removes that premise — git helpers land in their
  own module and `select-next-*` / `resolve-*` never import it — so the function-level import can go
  back to module scope where it belongs.
- `workhorse.testing`: `WorkflowRun` documents patching `scriptutil.github_client`, and that seam
  moves with the function.

**Deferred to the migration (found 2026-07-29, while building).** The split is blocked on the
YAML workflows, not on workhorse: **42 scripts under `base-library/workflows/` import a moving
name** (`resolve_workspace`, `open_repo`, the git helpers, the GitHub helpers), and coder's
`tests/conftest.py` monkeypatches `scriptutil.github_client` / `push_branch` / `sync_to_origin` on
the *module object*. That last one is what rules out a re-export shim: patching one module's
attribute cannot redirect another module's internal lookups, so the moment `resolve_repo` lives in
`kit` and calls `kit.github_client`, coder's 309-test suite talks to the real PyGithub. The split
therefore lands with the ports — each workflow's scripts become `kit` callers as that workflow is
ported — rather than as a step before them. Nothing about the destination changes; only when.

### What this leaves in the base library

Skills (`library/skills/`) and scaffolds — content that is genuinely data: human-authored, zero
dependencies, nothing to import, overlay-shadowed name-for-name, rendered into a repo by farrier.
The discovery/cache/layer machinery keeps earning its place for those.

**The skills stay in the base library, and the fetch narrows to them.** Decided (2026-07-29), and
this is what closes the trust question the flip raised. Today the base library is a git checkout of
this whole repo, which was tolerable while everything fetched was YAML and markdown and would stop
being tolerable the moment any of it were importable Python. Removing the workflows resolves it from
the other side: **what remains is markdown, so the fetch should take only the markdown.** A sparse
checkout of `library/` rather than the tree, and the cache holds documents rather than a repository.

The skills themselves are not up for relocation — they are stablemate's own content, they are what
farrier exists to install, and the overlay shadowing that makes them useful is a base-library
mechanism. Nothing about packaging the workflows argues for moving them.

Two properties this buys, both worth stating because they are the answer to "is fetching this
safe":

- **Nothing fetched is executable.** Code arrives only as a wheel from an index, under whatever
  supply-chain posture the operator already applies to `pip`/`uv` — a boring, existing answer,
  rather than a new one invented for a git cache.
- **The narrower checkout is smaller and its diff is reviewable.** A skills update is a markdown
  diff. That is a property to keep on purpose, since it is the thing that made "the library is
  data" true in the first place.

**Scaffolds do not move to the workflows package.** Four of the six are stack choices
(`flutter-app`, `go-service`, `pulumi-infra`, `react-router-web`) and a repo brings its own; a
workflow package that shipped them would be dictating a stack. They stay a farrier/library concern.

The two that are not stack choices need a different answer rather than a free ride:
`shared-docs.yml` seeds `docs/backlog.md` — which `author/scripts/load-config.py` **hard-exits**
without — and `docs/epics/`, which ostler's profile inference keys on (`full` when present,
`exploration` when not, and only `full` runs the structural doctor checks the coverage gate needs).
`qa-stack.yml` is read by `coder/scripts/ensure-stack.py`. A self-owning workflow expresses that as
a **declared repo input contract that fails loudly**, not as a scaffold it ships: the workflow
states what it requires of the repo and says so in one clear error, and creating those files stays
the operator's business. This also fixes the current shape, where the requirement is discoverable
only by reading a scaffold comment and hitting a `SystemExit` on the first run.

Workflows were the member of that set that never fit, and said so out loud in three places: a
`requires:` block that is a hand-rolled dependency manifest, a `scripts/` directory of Python that
`InProcessScriptRunner` imports and executes, and `pipx inject` in the README. Removing them does
not weaken the base library; it removes the thing that made "plain data" untrue.

Follow-ons: `is_library_dir` currently accepts "contains `library/` **or** `workflows/`" and must be
narrowed; `check_public.check_base_stands_alone` asserts the base ships workflows that resolve, and
that clause goes with them.

Worth confronting rather than assuming, since it is the premise the whole layer stack rests on:
after workflows leave, the base library is **nine `stablemate/*` skills and six scaffolds**, with no
`packs/`, no `prompts/`, no `roots/` — `base-library/library/` contains only `skills/`. Farrier
selection is pack-driven, and this repo's own `agents.yml` selects `python-workflow`, `stablemate`
and `testing`, none of which are in the base; stablemate cannot farrier-install *itself* without the
overlay. Whether nine self-hosting skills justify `LAYERS` / `find_in_layers` / `resolve_library_dir`
/ `base_cache` / `STABLEMATE_BASE_DIR` / `is_library_dir`, or whether the stack collapses to one
configured library directory, is a live question — see the open questions.

## Rejected along the way

- **States as thin module-level flows with typed payload models.** *(The previous draft of this
  document. Rejected on the evidence of the `author` rendering, which is why the artifact exists.)*
  A model per state means every state boundary has to be a place the payload makes sense, and that
  pressure fragments the machine: the first rendering came out at fifteen flows, most of them a
  single call wide. Deleting the models deleted the pressure, and `author` settled at nine states.
  The models were justified as the last place `dict[str, Any]` was hiding — `ParamSpec` answers
  that better, because the next state's signature is a schema that cannot drift from itself.
- **Mutable fields on the workflow class.** The intermediate draft put working state (`epic`,
  `story_slug`, rework counters, derived paths) on `self`. It is the run-context bag again, merely
  typed: any state can write it, so ambient coupling stays expressible and the checkpoint has to
  serialise the whole instance. Replaced by the three tiers above.
- **`self.call(node, args={...})`** — a dict erases the signature: no type check, no arity check,
  no jump-to-definition on a parameter, and a typo'd key is a runtime `KeyError` deep inside the
  callee. Recovering that checking is most of the reason to leave YAML.
- **`next` returned by every node** — a hidden `goto`. Control leaves the caller without the reader
  seeing it, and the code after the call becomes conditionally dead.
- **`await_operator` as a blocking node** — kept in the first rendering, then rejected: see
  "Waiting is a transition".
- **~~`workflow.handoff(fn, args={...})`~~ — un-rejected, with a narrower meaning.** The original
  objection stands against the original proposal: as a synonym for calling a flow, the verb was
  redundant and misleading. But the rendering found a gap it fits exactly. `Continue` can only name
  a method of *this* class, so nothing expresses what a YAML `flow:` node did — run a *different*
  state machine to its own `Done` and return the result. `author` needs it twice, for the
  `surveyor` and `parity-surveyor` sub-graphs. With that meaning the name is accurate rather than
  misleading: it *is* a transfer of control that returns only when the callee terminates. What it
  is **not** is a way to reuse the caller's environment — see below.

#### A sub-flow is independent

A handed-off flow resolves **its own registry**, and gets that registry's prompt directory, node
index and stand-ins. Registration travels with the class, the same way a node's registration
travels with the function, so `handoff(Surveyor, …)` finds the composition root `Surveyor` was
registered under rather than inheriting the caller's.

This is not symmetry for its own sake. Inheriting the parent's environment is already a bug in the
tree: `handoff` swaps only the writer, so a sub-flow living in another distribution renders its
prompts out of the *parent's* package directory — a path that either does not exist or, worse,
resolves to a same-named prompt belonging to someone else. The independence rule fixes that and
answers the node-index question in the same stroke.

The consequence worth stating plainly: **a parent's substitutions do not reach its children.** A
test that overrides `clone_repo` in the parent's index has said nothing about the child's, and a
test that wants both says so twice. That is the cost, and it is the right one — a sub-flow is a
different program, and a stand-in that leaked across the boundary would be a global under another
name, which is exactly what the index exists to abolish. A class with no registry of its own
inherits the caller's, which keeps a sub-flow declared beside its parent working with no ceremony.
- **`with w.match(...) / w.case(...)` builder blocks** — readable, and they force the pure-builder
  model (a context manager cannot skip its body; the `sys.settrace` recipes that fake it break
  under debuggers and coverage, which is disqualifying for a week-long unattended runner). But that
  model is the existing declarative design wearing new syntax, and it buys none of the dependency
  isolation.
- **Whole-workflow concolic tracing for `dot`** — exponential in total branch count, needs a fork
  budget so a `while` does not diverge, and produces phantom edges from independently forking an
  `if`/`elif` chain on one value. Superseded by per-flow enumeration above.

## Decided (2026-07-29)

Every question this document opened, answered. Each is written up where it belongs — this is the
index, not the argument.

| was open | decided | where |
|---|---|---|
| Does the base layer survive? | **Yes.** The skills are stablemate's own content and stay in the base library; nothing about packaging the workflows argues for moving them. | *What this leaves in the base library* |
| Trust posture on a git-fetched library | **The fetch narrows to the markdown.** A sparse checkout of `library/`, not the repo. Nothing fetched is executable; code arrives as a wheel, under the supply-chain posture the operator already has for `uv`. | *ibid.* |
| Step-key scheme / callsite fingerprinting | **Not built.** Resume does not inspect what the previous attempt completed — it calls the state again with those parameters. | *Resume* |
| Concurrency | **Out of scope.** Sequential only. Not a deferral to design later; parallel states are not a thing this engine has. | — |
| Migration: port or gradual? | **Gradual, and both front-ends coexist.** Build the new machinery per workflow, run them, assess, and delete the YAML path only once all four are proven. | *Migration* |
| Enforce "no mutable fields"? | **Yes — freeze the instance after `setup()`.** | *The rules resume imposes*, rule 3 |
| How large may a parameter be? | **As large as it needs to be, but keep checkpoints small**: bulk moves to `self.output(node, …)`, which reads a recorded output instead of copying it into the transition. | *The fourth thing, which is a read* |
| `Blueprint(requires=[...])` | **Not built.** `[project.dependencies]` is the manifest; a second one that can disagree is worse than none. | *The mechanism stays plural* |
| `Await` wait mechanism | **Synchronous polling, in-process.** inotify is Linux-only and the wait's latency budget is days. The 280 `ctypes` lines are deleted, not moved. | *Waiting is a transition* |
| Which invocation `self.output` resolves to | **The latest.** Last write wins, and a node that has not run raises rather than returning empty. | *The fourth thing, which is a read* |
| How state and node names get pinned | **`aliases=[…]` on the decorator.** Identity is the plain name; a resume that matches nothing fails loudly, and the alias is the fix. Nodes need it too, because `self.output` resolves by node name. | *The rules resume imposes*, rule 4 |
| Where the pure-git helpers land | **All of them in `kit`; workhorse keeps none.** `scriptutil.py` is the only module under `workhorse/workhorse/` that imports `git`, so the cut is total and the acceptance test is binary. | *The `scriptutil` split* |
| How a workflow's files are split | **Normative, not per-port taste.** `nodes/` is a package of subject modules even when small, `schemas.py` becomes `schemas/` on the same trigger, `workflow.py` is one class with no state mixins, tests live in `workflows/tests/<workflow>/` mirroring the node modules. `research` shipped flat and is restructured before `author` is ported. | *One workflow, several files* |
| What `registry.nodes` is for | **It is the composition root, and it is what runs.** `self.call` reads the function for its name and the run's index for the implementation; a name the index does not carry is an error naming `add_blueprints`. | *The node index is the substitution seam* |
| How a test replaces a node or the agent | **By supplying dependencies, never by patching.** `RunEnv` carries `nodes`, `agent_stubs` and `run_agent`; `Registry.override(...)` produces a substituted index. The two `patch()`es in the `research` suite are deleted, not relocated. | *ibid.* |
| What `--dry-run` runs | **A substituted index, not an engine branch.** Stand-ins come from `@blueprint.node(stub=…)` and `Registry.stub_agents({...})`, falling back to a blank return model. The fail-terminal exemption applies only while a registry declares no stand-ins. | *`--dry-run`, and what happens to `dot`* |
| What a sub-flow inherits from its caller | **Nothing but the run directory.** A handed-off class resolves its own registry, hence its own prompt root, node index and stand-ins; a parent's overrides do not reach it. A class with no registry of its own inherits the caller's. | *A sub-flow is independent* |
| `check_base_stands_alone` and unresolved skill names | **Not a gap — the referent is not the library's.** Workhorse resolves skills from the workspace it is installed into, never from the base library, so a prompt naming a skill the base does not carry is not a dependency on an overlay. | *below* |

### Migration

The earlier draft claimed both front-ends could not coexist, because the `Graph` model is what the
YAML loader produces and this design removes it. That is true of the *end state* and false of the
path: the new driver is additive, so `workhorse run` can dispatch on what a workflow *is* —
a `workflow.yaml` in a library directory, or an entry point resolving to a `Workflow` subclass —
and the two paths share nothing that needs reconciling. Nothing forces the deletion to happen
before the replacement is trusted.

So: build the driver, port one workflow, **run it in anger**, and only then port the next. The
`Fate: deleted` column in the engine table above stays accurate; it just describes the last step
rather than the first. Two conditions on the interim, since a maintained double front-end is how
this kind of migration stalls:

- **The deletion is the definition of done.** A YAML path kept "just in case" past the point where
  every workflow has a Python port is not caution, it is two engines. Name the four ports as the
  gate.
- **New capability lands only on the new path.** If both front-ends grow features, they stop being
  a migration and start being a fork — and `dot`, `testing.py` and the CLI each pay for it twice.

### The skill names in base prompts are not the base library's referents

This document twice called it a gap that `check_public.check_base_stands_alone` tests *resolution*
and not *referential completeness*: it passes while most of the skill names the base workflow
prompts mention resolve only in an overlay. That framing was wrong about where the referent lives.

**Workhorse resolves skills from the workspace it runs against — the installed skills of the repos
that workspace covers. It has no link to the base library at all.** The library is what farrier
installs *from*; what a prompt names is looked up in what was installed *into* the target. So a base
prompt naming a skill the base library does not carry is not a hidden dependency on a private
overlay — it is a workflow asking its workspace for something the workspace is expected to provide,
which is the same relationship every workflow has with the repo it operates on.

Two consequences, and neither is work for this design:

- **The check's subject is correct as written.** It asks whether the base library resolves standing
  alone — its own skills, its own workflows, no overlay configured. That is the public/private
  property, and it is the whole property. Adding a name-crawl over prompt bodies would not make it
  stronger; it would make it wrong, by asserting a containment the architecture does not have.
- **The residual risk is real but belongs elsewhere.** A prompt naming a skill no workspace installs
  fails at run time, late and confusingly. That is a workspace-configuration diagnostic — farrier's
  or a doctor's — not a public-split one, and it is out of scope here.

## Still open

Nothing in the design. One thing in the artifact: `docs/plans/author-workflow-python/workflow.py`
still writes `_unblock` as a blocking `self.call(scriptutil.await_operator, …)`, marked SUPERSEDED
in place rather than converted. Converting it is not a substitution — an `Await` can only be
*returned*, so every caller must propagate it, which splits each calling state in two. Worth doing
if the artifact is going to be read as the shape rather than as the census; skip it if the driver is
about to be built anyway and will settle the question in code.

## Suggested first step

Build the driver, `@workflow.main`/`@workflow.node`, `Continue`/`Done`/`Await`, and `--dry-run`
against a port of `research/workflow.yaml`. It is the smallest workflow that exercises branches, a
bounded rework loop, counters, and sub-flows — i.e. every construct the design claims to improve —
and the counter machinery it would delete is the concrete before/after.

Two constraints on that first step, both learned from the `author` rendering:

- **`Await` goes in the first driver, not a later one.** It is a third `Transition` arm, so
  `drive()` and the checkpoint schema are shaped by it; bolting it on afterwards means rewriting
  both, plus every state that was written to block inline.
- **The largest case is already rendered.** [`author-workflow-python/`](author-workflow-python/)
  exists so the design can be judged against 159 nodes rather than 508 lines, and `research` is the
  build target only because it is the cheapest thing to make *run*. If a driver decision makes
  `author`'s nine states awkward, that outranks whatever `research` was comfortable with.

## Execution loops

Four `/loop` runs, split at the point where the old front-end must start coming down. The split is
load-bearing: everything in loops 1 and 1.1 lands **beside** the YAML engine with it still green,
so the work is revertible one commit at a time. Loop 2 is where that stops, and it is now the
*only* place it stops — the ports were originally the first half of loop 2, which put the point of
no return *inside* a loop rather than at its boundary. Loop 1.1 pulls every port out in front of
every deletion, so loop 2 opens on a checkable precondition (all four workflows run on the driver)
and everything it does is irreversible by design. Loop 3 changes no behavior at all: it makes the
tree say what the code now does.

The price of that ordering, named so nobody is surprised by it: for the length of loop 1.1 the tree
carries two engines and `make test` runs both suites. That is the cost of being able to revert any
single commit, and it is worth paying.

`research` is the *last* step of loop 1, not the first of loop 2. Porting it is migration in the
literal sense, but its purpose here is proof: an unproven driver is not a finished driver, and the
cheapest honest test of "the machinery is done" is one real workflow running on it. Move it into
loop 2 if you would rather loop 1 end on unexercised code.

### Context discipline, which each prompt repeats

Loop 1's first run compacted itself to a standstill, and the cause was in the prompt rather than in
the work. Three lines drove it, and every prompt below carries the fix:

- **"Read the plan first"** pointed at this file — ~1,350 lines, ~25k tokens, re-read every
  iteration on top of a 1,500-word instruction block. Each prompt now names the *sections* it needs
  instead, and forbids reading the whole thing.
- **Nothing recorded progress.** With no ledger, an iteration that woke up after a compaction
  rebuilt its state by re-reading the plan, re-reading the engine, and re-running the suites — and
  that rediscovery is precisely what filled the context that triggered the next compaction.
  [`workflow-as-python-state-machine-progress.md`](workflow-as-python-state-machine-progress.md) is
  now the ledger, and writing it is part of every commit.
- **Iterations ended with a dirty tree**, so `git log` could not answer "what is done" either. The
  commit is no longer the iteration's reward; it is its terminator.

A fourth cost was self-inflicted: `make test` runs six subproject suites plus the workflow suites,
bench, and `check-public`, and every passing line of that was read into the context. Redirect it and
read only the tail on failure. The green bar does not move — only what is paid to observe it.

The failure this prevents is not slowness. Loop 1's post-compaction iterations re-derived
`research/models.py` as 224 lines of typed payload models passed between states — the shape this
document lists under "Rejected along the way". A loop that has lost its decisions does not stall
visibly; it rebuilds what was already rejected, confidently.

### Loop 1 — build the machinery, keep the YAML engine green

```
/loop Work docs/plans/workflow-as-python-state-machine.md to the point where the new
machinery is built and proven, WITHOUT starting the migration.

START by reading docs/plans/workflow-as-python-state-machine-progress.md — the ledger. It
records what has landed, what is next, and which decisions were re-confirmed; it is the
only file you should need to reconstruct where this loop is.

Then read ONLY these sections of the plan: "The shape to build", "Packaging and
distribution", "farrier keeps no workflow knowledge", "Suggested first step", "Decided
(2026-07-29)" and "Rejected along the way". Those are decisions, not suggestions. Do NOT
read the file end to end — it is ~1,550 lines, and re-reading it every iteration is what
drove the first run of this loop into repeated autocompaction. Open another section only
when the step you are on names it.

Deliver, in dependency order — one focused commit per iteration:

1. The `workhorse-workflows` distribution skeleton: `workflows/` as a uv workspace member,
   `src/workhorse_workflows/`, the `[project.entry-points."workhorse.workflows"]` table,
   and entry-point discovery in workhorse so `workhorse run <name>` resolves a package.
   `workflow_dir` must stay a real directory — add the test that a zip-imported package
   fails loudly rather than at TemplateNotFound time.
   Plus the `[project.scripts]` table: one `workhorse-<name>` console script per workflow,
   pointing at `…workflow:main` — see "Each workflow gets a console script". `main` must be
   the callable `workflow.main(Entry)` RETURNS, not a call made at import. Acceptance:
   `workhorse-<name> run <flow> --run-id=… --params …` and `workhorse run <name> <flow> …`
   go through one parser with the name bound differently — assert it, because two commands
   with two parsers is the failure this shape invites.
2. The `scriptutil` split. Domain half (github_client, resolve_github_token, find_open_pr,
   push_branch, sync_to_origin, build_dispatch_list, get_affected_repos, resolve_workspace,
   checkout_workspace) moves to `workhorse_workflows/kit/`; engine-side seams (run_tool,
   fresh_import, find_repo_root, load_json, die) stay. The pure-git helpers (open_repo,
   checkout, commit_all, clone, fetch_reset, current_branch, rename_branch, default_branch)
   go to `kit` too — ALL of them; workhorse keeps none. `find_repo_root` stays and is not
   an exception: it walks parents for `agents.yml` or `.git` and never touches GitPython.
   Acceptance: `gitpython` and `PyGithub` leave workhorse-agent's required dependencies,
   and no module under `workhorse/workhorse/` imports `git`. `workhorse.testing`'s
   documented `scriptutil.github_client` patch seam moves with it. Collect on the way past:
   `open_repo`'s lazy `from git import Repo` returns to module scope, since the split
   removes its premise.
3. farrier decoupling, per the fate table in "farrier keeps no workflow knowledge".
   `collect_template_values` SURVIVES — it reads `vars:`/`template:` from agents.yml and is
   only misfiled. Move launcher/compose generation into the package; do not delete it.
4. The missing-`instruction_ref` validation, reborn in workhorse at render time / under
   `--dry-run`. This is a real bug guard, not cleanup: an unresolved reference currently
   renders the prose string "generated <name> instruction file when installed" into a live
   agent prompt, silently.
5. The driver: `@workflow.main` / `@workflow.node`, blueprints, `Continue` / `Done` /
   `Await` / `WorkflowFailed`, `drive()`, `self.output()`, and the `(state, params)`
   checkpoint. Five things are decided and not open for rediscovery: `Await` ships in the
   FIRST driver (it is a third Transition arm, so it shapes `drive()` and the checkpoint
   schema, and retrofitting means rewriting both); its wait is a portable polling loop, NOT
   inotify; resume is coarse with NO intra-state memo and no callsite fingerprinting; the
   `Workflow` instance FREEZES after `setup()` returns; and both `@workflow.state` and
   `@blueprint.node` take `aliases=[…]`. Acceptance on the last one: a checkpoint naming a
   dead state fails loudly rather than starting over, declaring the old name as an alias
   resumes it, an alias colliding with a live name raises at registration, and `dot` /
   `--dry-run` render live names only.
6. `--dry-run` and per-flow `dot` enumeration against the new model.
7. Port `research/workflow.yaml` (508 lines) as the proof, and show the counter machinery
   it deletes as a concrete before/after.
8. Wire the registry as the composition root — added 2026-07-29, after the port showed the
   node index was write-only. `RunEnv` carries `nodes` / `agent_stubs` / `run_agent`;
   `self.call` resolves the stamped NAME through that index and errors on a name
   `add_blueprints` never folded in; `--dry-run` becomes a substituted index rather than an
   `if` inside `Engine.call`; a handed-off class resolves its own registry, hence its own
   prompt root and node table. Acceptance: `research`'s suite substitutes no *seam* by
   patching — no agent runner, no node, no engine attribute — and `--dry-run` reaches
   `Done` on a registry that declares stand-ins. What legitimately remains is
   `patch.object(research, "MAX_REWORKS", 2)`, which lowers a cap so a test spends three
   loops rather than four, and a wrapper on `ArtifactWriter.write_state_checkpoint` that
   *observes* what was written. Neither replaces a dependency. See "The node index is the
   substitution seam".

Each iteration ends green AND ends committed. `ruff check .` from the repo root (zero
findings, fix rather than noqa), then `make test && make check-public
>/tmp/wf-loop1-test.log 2>&1 || tail -80 /tmp/wf-loop1-test.log` — redirect it and read
the tail only on failure, because six subproject suites of passing output is a large share
of the context this loop needs to keep. Tests dependency-free and standalone per
workhorse/CLAUDE.md. The YAML engine keeps working the whole way — if a step cannot land
without breaking it, that step belongs in loop 2; say so and move on.

Then commit, and update the ledger in that SAME commit: what landed, what is next, and any
decision you had to go back to the plan to re-confirm. Never end an iteration with a dirty
tree — uncommitted work stops `git log` from answering "what is done", so the next
iteration re-derives it from source, and that rediscovery is what fills the context. If
you cannot get to a committable state, stop and say why rather than carrying WIP forward.

STOP and ask me if a driver decision makes `author`'s nine states awkward — check against
docs/plans/author-workflow-python/, which outranks whatever `research` liked. Nothing else
in this loop is open by design; if you find something that is, stop rather than picking.

Everything this plan once listed as open is now DECIDED — see "Decided (2026-07-29)". The
skills stay in the base library; nothing fetched is executable; `self.output(node, …)`
reads the latest invocation and raises when the node has not run; names are pinned with
`aliases=[…]`; every pure-git helper leaves workhorse. Do not reopen any of them.

Do NOT touch in this loop: graph/loader.py, graph/nodes.py, base-library/workflows/*
beyond research, or anything in the loop 2 deletion list.

End the loop when research runs end-to-end on the new driver with the YAML engine still
green, and report what is left for loop 2.
```

#### Resuming loop 1 mid-flight — HISTORY, loop 1 is complete

**This prompt has been run and loop 1 is done** (`5d3f89d`, `772b5d0`, `2ea582a`, `2637034`; see
the ledger). It is kept only because it is the worked example of restarting a stalled loop, and
because the diagnosis below is the case study behind "Context discipline" above. Do not fire it.

The first run landed steps 1, 3, 4, 5 and 6 — `740a6ef`, `7cae8d1`, `5bb7e29`, `ea47ff7`,
`53dc4ba`, or 2,350 lines under `workhorse/workhorse/pyflow/` — then stalled inside step 7 with
**step 2 never done**. That skip is itself a symptom: `research/nodes.py` imported `checkout`,
`clone`, `commit_all` and `fetch_reset` from `workhorse.scriptutil`, which is exactly the module
step 2 empties, so the port was being written against a seam that was scheduled to move.

Do **not** re-fire the prompt above to finish this. Most of it specifies committed work, and
re-reading a spec for finished work is the cost that stalled the run. Use this instead:

```
/loop Close out loop 1 of docs/plans/workflow-as-python-state-machine.md. Two steps
remain: step 2 (the scriptutil split), which was skipped, and step 7 (port `research` as
the driver's proof), which is in flight. Steps 1, 3, 4, 5 and 6 are committed — the driver
is 2,350 lines in workhorse/workhorse/pyflow/ and is not being redesigned here.

Read docs/plans/workflow-as-python-state-machine-progress.md first — the ledger — then the
driver source. From the plan read ONLY "The shape to build", "The `scriptutil` split",
"Decided (2026-07-29)" and "Rejected along the way". Do NOT read it end to end: it is
~1,350 lines and re-reading it each iteration is what stalled the first run.

FIRST, settle the in-flight work rather than building on it.
workflows/src/workhorse_workflows/research/models.py is 224 lines of typed models
declared as "every typed value the research workflow moves between its states" — which is
what "Rejected along the way" rejects and what the 2026-07-29 revision says was removed.
Decide whether these are the rejected thing (typed payloads at state boundaries, which go)
or merely agent-reply validation (which may stay, under a name that does not claim
otherwise). Say which, and do not port further until it is settled.

Then, in this order, one commit each:

1. Step 2, BEFORE finishing the port, because the port already imports four of the
   helpers it moves — doing it after means rewriting nodes.py. Domain half to
   workhorse_workflows/kit/, engine-side seams stay, ALL pure-git helpers leave.
   Acceptance: gitpython and PyGithub leave workhorse-agent's required dependencies and
   no module under workhorse/workhorse/ imports git — including the lazy function-level
   `from git import Repo` in scriptutil, which returns to module scope in its new home.
2. Step 7: finish the port and make it run end-to-end. Show as a concrete before/after
   the counter machinery it deletes — init_lead_counter, init_extend_counter,
   reset_rework, guard_rework, and the max_reworks constant kept in sync by comment.

Each iteration ends green and ends COMMITTED: `ruff check .` from the repo root, then
`make test && make check-public >/tmp/wf-loop1-test.log 2>&1 || tail -80
/tmp/wf-loop1-test.log`. Update the ledger in the same commit. Never carry a dirty tree
into the next iteration.

STOP and ask me if the port makes a driver decision look wrong — the driver is proven by
this port, not renegotiated by it.

End the loop when research runs end-to-end on the driver with the YAML engine still green,
and write loop 2's starting state into the ledger.
```

### Loop 1.1 — port every workflow, decommission nothing

Loop 1 proved the driver on one workflow. This loop ports the other three and stops there: **no
deletion, no narrowing, no doc correction that presumes a deletion.** The YAML engine keeps running
the whole way, both front doors resolve, and every commit is revertible on its own.

The ordering inside is not arbitrary, and `research` is the reason. It exercised branches, a bounded
rework loop, counters and twelve states — but nothing in it waits on a human and nothing in it calls
a sub-workflow, so two of the driver's three transition arms have never run against a real workflow.
`Await` exists at `pyflow/transitions.py:107` and `self.handoff(...)` has a graph edge, and both are
still theory. What the remaining YAML actually needs:

| Workflow | YAML | scripts | `await-operator` sites | `type: flow` nodes |
|---|---:|---:|---:|---:|
| `author` | 2,116 | 23 (+25 under `surveyor/`) — 5,695 lines | 12 | 2 |
| `okf-builder` | 729 | 11 — 1,723 lines | 0 | 1 |
| `coder` | 4,366 | 71 — 8,661 lines | 19 | 8 |

So `author` goes first: it is the first workflow to exercise `Await` *and* `handoff`, and an
`Await` defect found there costs one port to fix where the same defect found in `coder` costs three.
The rendered artifact under [`author-workflow-python/`](author-workflow-python/) means it is also
the one port that is a transcription rather than a design exercise. `okf-builder` is second because
it is cheap and consolidates. `coder` is last on the old grounds — largest, and the only one
carrying the docker/stack machinery — but now also because by then every construct it uses has been
built once already.

```
/loop Port the remaining three workflows in docs/plans/workflow-as-python-state-machine.md
onto the Python driver. Loop 1 built the driver and proved it on `research`. This loop
DELETES NOTHING: the YAML engine stays green and fully usable until loop 2, and any step
that cannot land without breaking it is a finding to report, not a step to force.

START by reading docs/plans/workflow-as-python-state-machine-progress.md — the ledger loop
1 left behind. It carries loop 1's final report, what is next, and the decisions already
settled; keep writing it here, in the same commit as the work.

Then read the ported `research` workflow — its nodes, schemas and workflow modules plus its
tests under workflows/tests/ — because it is the worked example every other port follows for
node contracts, state shape and test pattern. It is NOT the example for FILE LAYOUT: it
shipped flat and step 0 below restructures it. From the plan read ONLY "The shape to build",
"One workflow, several files", "Resume", "Packaging and distribution", "Decided
(2026-07-29)" and "Rejected along the way". Do NOT read the plan end to end: it is ~1,650
lines, and re-reading it each iteration is what stalled loop 1's first run. A port question
is answered by `research` and the driver source first, by the plan only when neither settles
it.

Port in this order, one workflow per iteration, each landing green before the next:

0. Restructure `research` into the layout in "One workflow, several files" — `nodes/` as a
   package of subject modules, tests as `workflows/tests/research/` — BEFORE porting
   anything else, because every later port copies the shape it finds and `author` is 48
   scripts totalling 5,695 lines. No behavior change, one commit: 316 lines of nodes.py
   become two node modules, and the 404-line test file splits to mirror them. Doing it now
   costs one port; doing it after `coder` costs four. The layout is decided, not a
   per-workflow judgement call — one subject per module, ~400 lines is the trigger to apply
   that rule, `workflow.py` holds one class and NO state mixins, `schemas.py` becomes
   `schemas/` on the same trigger, and every part that grows is a directory before it has
   to be.
1. `author` — 2,116 lines of YAML, 23 scripts (2,653 lines) plus 25 more under
   `surveyor/` (3,042 lines) that are author's too and are easy to miss. It is FIRST
   because it is the first workflow to exercise `Await` (12 await-operator sites) and
   `handoff` (2 `type: flow` nodes), neither of which `research` touched — find a defect in
   those arms here, where it costs one port, not in `coder`, where it costs three. The
   whole workflow is ALREADY RENDERED in docs/plans/author-workflow-python/: that is the
   reference, not a fresh design exercise. Where the port diverges from it, say why.
2. `okf-builder` — 729 lines, 11 scripts, no awaits, 1 sub-flow. The cheap one; it should
   mostly confirm what author settled.
3. `coder` — 4,366 lines, 71 scripts (8,661 lines), 19 awaits, 8 sub-flows, and the only
   docker/stack machinery. Last, so it inherits every lesson. It is also the size test: if
   `self.output(node)` or the state-granularity rule breaks down anywhere, it breaks here.

Each port produces the whole package — workflow.py holding only the class, nodes/ grouped by
subject, schemas, paths.py for the derivations the three-tier rule pushes out, flows/ for
each `type: flow` sub-graph, one `[project.entry-points."workhorse.workflows"]` line, one
`[project.scripts]` console script, and tests under workflows/tests/<workflow>/ mirroring
the node modules plus one module for the machine itself. Take research's test file as the
pattern for what goes INSIDE each: real nodes against a temp git repo with only the agent
turn scripted. That pattern is what made research's claims checkable, and a port without it
is a port whose parity is an assertion. One node module per subject and one test module
beside it is what keeps `coder`'s 71 nodes reviewable — a single nodes.py at that size is
scriptutil.py again, which is the module this whole packaging argument exists to unmake.

Parity is the gate, and "it runs" is not parity. For each workflow demonstrate that the
ported flow produces the same artifacts and the same resume behavior as the YAML for at
least one real run, and record the evidence in the ledger. A behavior you cannot reproduce
is a finding to report, not a difference to absorb silently. Both engines are present for
the whole loop, so this comparison is available — that is the main thing this ordering buys,
and taking a port on faith wastes it.

`await-operator.py`'s 280 lines of ctypes inotify do NOT get ported — the driver's portable
polling wait replaces them. Deleting them is loop 2's; leaving them unported and unused is
this loop's.

Each iteration ends green AND ends committed. `ruff check .` from the repo root, then
`make test && make check-public >/tmp/wf-loop11-test.log 2>&1 || tail -80
/tmp/wf-loop11-test.log` — redirect it, read the tail only on failure. Note that this bar
covers BOTH engines for the length of this loop; a YAML suite that goes red is a
regression, not an expected casualty.

STOP and ask me before: deleting or narrowing anything at all, changing the driver API (it
invalidates the ports already done, so it is my call), and porting a behavior you cannot
find a home for in the new shape.

End the loop when all four workflows resolve through `workhorse.workflows` entry points and
run on the driver, each with parity evidence in the ledger, with the YAML engine still
green and nothing deleted. Then write loop 2's starting state: the deletion list, and
anything found during porting that belongs on it.
```

### Loop 2 — decommission the YAML front-end

Loop 1.1 ends with two working engines and a checkable precondition. This loop is the irreversible
one, and it does nothing but subtract. Its entry gate is loop 1.1's exit condition: all four
workflows on the driver, each with parity evidence. If that evidence is missing for any workflow,
this loop does not start — it sends the workflow back.

```
/loop Decommission the YAML front-end, per docs/plans/workflow-as-python-state-machine.md.
Loop 1.1 ported all four workflows onto the driver and deleted nothing; this loop is the
deletion, and it is the irreversible half.

START by reading docs/plans/workflow-as-python-state-machine-progress.md — the ledger,
which carries loop 1.1's deletion list and the parity evidence for each port. CHECK THAT
EVIDENCE FIRST: a workflow without recorded parity is not ready to have its YAML deleted,
and the right move is to say so and stop, not to delete and find out. From the plan read
ONLY "Packaging and distribution", "What this leaves in the base library" and "Migration".

Delete in this order, each its own commit:

- `graph/loader.py` (45), `graph/nodes.py` (256); rewrite `graph/dot.py` (297) against the
  new model; rework `main.py`'s `_step_loop`/resume; trim `testing.py` (575) to what a
  callable flow still needs.
- `base-library/workflows/` and the `requires:` handling that was its hand-rolled
  dependency manifest.
- The now-dead library plumbing: narrow `is_library_dir` (it currently accepts "contains
  library/ OR workflows/"), drop the workflow clause from
  `scripts/check_public.py::check_base_stands_alone`, and remove the `.agents/workflows`
  legacy cleanup from farrier's outputs once a release has passed.
- Narrow the base-library fetch to a sparse checkout of `library/`. This is the decided
  trust posture and it can only land here, once `base-library/workflows/` is gone: what
  remains is markdown, so the cache should hold documents rather than a repository.
- `await-operator.py`'s 280 lines of ctypes inotify, per workflow. Loop 1.1 left them
  unported on purpose; the driver's polling wait is their replacement.
- Correct — do not rewrite — the docs that would otherwise describe a deleted front-end as
  current: docs/features/workhorse/workflow-format.md, base-library/workflows/README.md,
  workhorse/README.md, workhorse/CLAUDE.md's graph-walk description. Enough that no
  committed file is actively false at the moment the deletion lands; the full documentation
  pass is loop 3's, and doing it here means writing it mid-deletion.

Each iteration ends green AND ends committed. `ruff check .` from the repo root, then
`make test && make check-public >/tmp/wf-loop2-test.log 2>&1 || tail -80
/tmp/wf-loop2-test.log` — redirect it and read the tail only on failure. Commit, and update
the ledger in that same commit: what was deleted, what it took with it, what is next. Never
end an iteration with a dirty tree — this is the loop where a dirty tree is worst, because a
half-finished deletion is the one state neither engine can be trusted in. Keep
workhorse/README.md and workhorse/docs/GUARDRAILS.md current as behavior changes — they are
the operator contract.

STOP and ask me before: deleting anything not on the list above, and any moment a deletion
suggests the driver API itself is wrong. Nothing here is meant to change the driver — if
subtracting the YAML exposes something the ports were quietly relying on, that is a finding
and my call, not a fix to improvise.

End the loop when no YAML front-end remains, all four workflows still resolve through
`workhorse.workflows` entry points and still run, and the 7,719 lines of workflow YAML are
accounted for — deleted, ported, or explicitly kept with a reason.
```

### Loop 3 — make the tree say what the code does, at a public bar

Loop 2 ends when the code is right. That is not the same moment the repo *reads* right, and
merging the two is how documentation gets written in the voice of whoever was mid-port: accurate
about the diff, silent about the whole. Separating them also separates two different judgements —
*is this correct* is answered against the code, *is this worthy of a public repo* is answered
against a reader who has never seen it.

The order inside the loop is not cosmetic. **Skills come before prose**, because a stale skill is
worse than stale prose: `stablemate-workhorse-scripting` teaches the stdout-JSON protocol, so
until it is rewritten every agent that reads it produces node code that cannot work. Stale prose
merely misleads a human, who can look at the source; a stale skill actively manufactures wrong code.

```
/loop Bring the repository's documentation, examples and skills in line with the Python
workflow design in docs/plans/workflow-as-python-state-machine.md, to a standard fit for a
public repository. Loops 1, 1.1 and 2 shipped the code. This loop changes NO behavior — if a doc
can only be made true by changing code, that is a finding to report, not a change to make.

START by reading docs/plans/workflow-as-python-state-machine-progress.md — the ledger,
carrying loop 2's final report and what each port actually settled. Then work from the
SHIPPED CODE: what the docs must now describe is what loops 1 and 2 built, and where the
plan and the code disagree the code wins and the disagreement is worth a line in the
ledger. Read the plan only to recover intent behind something the source leaves ambiguous,
and then only the section that covers it — never the whole file, which is ~1,650 lines and
whose repeated re-reading drove loop 1 into autocompaction.

Work in this order — one focused commit per iteration:

1. THE SKILLS FIRST, because an agent reads them and a wrong one manufactures wrong code.
   Edit base-library/library/skills/stablemate/** — the SOURCE. .claude/skills/** is
   farrier's installed copy; re-install to refresh it, and if the two have drifted, say so
   rather than hand-editing both.
   - stablemate-workhorse-scripting (418 lines) is a rewrite, not an edit. Its spine is the
     "stdout must be valid JSON matching outputs:" protocol, which does not survive: a node
     returns a typed model. What DOES survive is `main(logger)` — the design chose that
     contract precisely so today's scripts port as-is — and the separation-of-concerns
     section, which is about workhorse being generic and is unaffected. Its `applyTo`
     glob (`scripts/**/*.py`) no longer describes where nodes live.
   - stablemate-coder-workflow and stablemate-okf-modeling reference workflow.yaml and
     node types; correct them without turning them into engine documentation.
2. workhorse/docs/WORKFLOW.md (482 lines) — the YAML schema reference. Rewrite rather than
   patch: a schema reference for a schema that no longer exists has no salvageable spine.
   Its successor documents the Python API — Workflow/Blueprint, states as methods,
   Continue/Done/Await/WorkflowFailed, self.call/agent/handoff/output, aliases=[...], the
   (state, params) checkpoint, and the two CLI front doors. Carry over the parts that are
   unchanged rather than rewriting them from memory: prompt rendering and the Jinja
   context, power tiers, output defaults. `labels:` and per-node `power:` were YAML blocks
   and are now something else; document what loop 2 actually built, and if it built nothing
   for them, that is a finding.
3. docs/features/workhorse/ — the OKF book, including workflow-format.md (164 lines), which
   loop 2 only corrected far enough not to be false. concepts/ entries are grounded in
   symbols loop 2 deleted or rewrote (load-workflow, evaluate-branch, dot-renderer, run-flow, run-call,
   run-script, workflow-context, testing, scriptutil), and flows/ walkthroughs narrate the
   old CLI (workhorse-setup-and-run, workhorse-author-test, workhorse-author-visualize-run,
   workhorse-crash-resume). Use `ostler` to find what dangles — that is what it is for, and
   if it cannot report this, say so instead of grepping around it. Regenerate grounded
   content with the builder rather than hand-writing it.
4. Every runnable example, and the invocations around them. `workhorse --workflow
   ./wf/workflow.yaml` is wrong wherever it appears: README.md, base-library/README.md,
   base-library/workflows/README.md, workhorse/README.md and workhorse/CLAUDE.md,
   saddlebag/README.md, farrier/docs/LAYOUT.md, workhorse/docs/DOCKER.md and GUARDRAILS.md.
   The quick-start example must EXIST and RUN — a smallest-possible workflow someone can
   copy is the single thing a public reader judges the project on, and a quick start that
   cannot be pasted is worse than none. Regenerate any committed `dot` output.
5. The public bar, which is a different pass and deserves its own iterations:
   - A reader arriving cold from GitHub or PyPI must get from install to "a workflow of my
     own that runs" using the docs alone. Today that path quietly assumes a private overlay
     exists. Walk it yourself on a clean checkout and fix what you hit.
   - Motivate the design ONCE, in one place, and link to it. Five READMEs each re-arguing
     why workflows are Python is how a repo reads as unfinished.
   - Placeholders only, per the root CLAUDE.md: acme, globex, api-service, example.com. The
     temptation in a docs pass is to document the real setup — do not. `make check-public`
     is the gate and it only sees TRACKED files, so run it, do not assume the hook covered
     it.
   - Check the cross-repo links (workhorse/README.md points at github.com/... blob/main
     paths); files moved in loop 2, and those break silently.
   - Anyone holding a YAML workflow needs to be told it is gone and what replaces it. A
     migration note is a public obligation, not an internal one.
6. This plan and docs/plans/author-workflow-python/ become history. Mark them implemented
   with a pointer to the shipped docs, or delete them. A plan still written in future tense
   about work that has shipped misleads every reader who finds it first.

Each iteration ends green AND ends committed. `ruff check .` from the repo root, then
`make test && make check-public >/tmp/wf-loop3-test.log 2>&1 || tail -80
/tmp/wf-loop3-test.log` — redirect it, read the tail only on failure. Commit, and update
the ledger in that same commit with what was corrected and what was found untrue. A docs
pass touches many files at once, so a dirty tree here is especially expensive: the next
iteration cannot tell a rewritten doc from an abandoned one without re-reading both.

STOP and ask me before: adding engine capability to make a doc claim true (that is loop 2
reopened, and it is my call), and before deleting any doc whose subject survives under a new
name — rewrite those.

End the loop when no tracked file describes the YAML front-end as current, `ostler` reports
no dangling references (or the remainder is listed with reasons), and someone who has never
seen this repo can install it, run the shipped example, and write a new workflow from the
docs alone.
```
