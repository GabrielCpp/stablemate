---
name: workhorse-engine
description: "Writing workhorse workflow nodes: the @blueprint.node contract, typed returns, WorkflowFailed routing, kit helpers, the ostler facade and substitution tests. Load when writing or testing a workflow distribution's Python."
applyTo: "**/workhorse_workflows/**/*.py, **/nodes/**/*.py, **/flow.py, **/workflow.py"
tags: [backend, standards, tests]
---

# Workhorse workflow nodes

A workflow is a **Python package**, not a YAML document. Its states are methods on a
`Workflow` subclass; its side-effecting work lives in **node functions** registered on a
`Blueprint`. There is no `workflow.yaml`, no `script:` node, no `outputs:` list, and no
stdout protocol — a node **returns a typed value**.

The engine API is documented in `workhorse/docs/AUTHORING.md`; this skill is about the
code you write against it.

---

## Separation of concerns — workhorse is generic, keep workflow logic in the workflow

Workhorse (`workhorse/**`, including `templates.py`, the pyflow driver,
and the Jinja globals it registers) is a **generic engine shared by every workflow**. It
must never learn the shape of one workflow's data.

**Do not add workflow-specific logic to workhorse.** Concretely, do not put in workhorse:
- a schema of a particular `plan-context.json` / plan_result (e.g. `services[].type`,
  `touched_layers`, layer→platform maps) — that is the coder workflow's vocabulary;
- a Jinja global that derives a workflow-specific value (e.g. `touched_layers()`); or
- branching on a specific env var name, repo name, or story convention.

**Where each thing lives:**
- **Deriving a value from the workflow's own data** → do it in the **workflow**: either in
  a `@blueprint.node` function that reads the JSON and returns the derived field, or
  directly in the prompt's Jinja over the args the state passes
  (`{% raw %}{% for svc in plan_result.services %}{% endraw %}` / `| map(attribute='type') | unique`).
- **A genuinely reusable primitive** → add it to workhorse **parameterised**, with no
  knowledge of any workflow's field names. `find_repo_root(repo_dir)` is the model: the
  workflow passes the path it already holds as a field, and workhorse resolves the argument
  it's told to — it reads no environment and knows no workflow's vocabulary. Good additions
  are things like "read a dotted path from a JSON file", "dedup a list preserving order" —
  verbs, not nouns from a specific schema.

Litmus test before touching `workhorse/**`: *would a totally different workflow want this
unchanged?* If it only makes sense for the coder workflow, it belongs in the workflow.

---

## Where a flow lives

Where a new flow, its prompts and its tests go is in [references/where-a-flow-lives.md](references/where-a-flow-lives.md). Open it before you add a workflow or move code between packages.

## The node contract

```python
from __future__ import annotations

import logging

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.acme.shared.blueprint import blueprint
from workhorse_workflows.acme.shared.schemas.plan import Validation


@blueprint.node
def validate_plan(logger: logging.Logger, spec_dir: str) -> Validation:
    logger.info("validating %s", spec_dir)
    errors = [...]
    return Validation(status="invalid" if errors else "valid", errors=errors)
```

- **`logger` is the first parameter, injected by the engine.** Never construct one, never
  call `logging.basicConfig` — the driver owns handlers, level (`WORKHORSE_LOG_LEVEL`) and
  the OTel export, and a node's records ride the driver's root logger with the run's
  `run_id` and node attribute already stamped.
- **Every other parameter is supplied by the caller**: `self.call(validate_plan, spec_dir)`.
  Arguments are ordinary Python values — no Jinja, no `sys.argv`, no argparse.
- **The return annotation is required and is the node's real output contract.** The
  decorator resolves it (`eval_str=True`, so `from __future__ import annotations` is fine)
  and keeps it: it is what `self.output(node)` revives an `output.json` back into, and what
  `--dry-run` blanks. A pydantic `BaseModel` is the intended shape; dataclasses, dicts and
  scalars are projected too, but only a model round-trips as a typed value.
- **Nothing is printed to communicate.** The engine records `jsonable(return_value)` to the
  node's `output.json` itself. `print()` in a node is a diagnostic at best; use `logger`.
- **`raise WorkflowFailed(reason)`** ends the run with that reason. There are no exit codes
  and no `SystemExit`; `raise SystemExit` inside a node kills the driver's own process and
  loses the checkpoint.

### Porting a `main(logger)` script

The old `script:` nodes were already `def main(logger)`. That contract was chosen so they
port with the envelope stripped and nothing else:

1. rename `main` to something that says what it does, and decorate it `@blueprint.node`;
2. delete the `argparse` / `sys.argv[1:]` preamble — those become named parameters;
3. delete the final `print(json.dumps({...}))` — return the model instead;
4. add the return annotation;
5. replace `raise SystemExit(1)` with `raise WorkflowFailed("…")`.

The body in between does not change.

### Decorator options

```python
@blueprint.node(aliases=["old_name"], retries=2, stub=lambda logger, **kw: Report(ok=True))
def check_stack(logger: logging.Logger, manifest: dict) -> Report: ...
```

- `aliases=[…]` — the names this node used to have. `self.output(node)` resolves by node
  name against the run directory, so renaming a node without an alias orphans a mid-week
  run's recorded outputs exactly as renaming a state breaks its checkpoint.
- `retries=N` — re-calls on exception before the failure propagates. `0` (the default)
  means call once.
- `stub=…` — what `--dry-run` calls instead, same signature. Declaring one turns a dry run
  from "every branch takes an arbitrary path" into a real smoke test of the happy path;
  without one the node yields a blank instance of its return model.
- There is deliberately **no `timeout=`**. A node runs in the engine's own process and
  there is no portable way to interrupt it, so the knob would be accepted and ignored. The
  run-wide `WORKHORSE_MAX_RUNTIME_S` budget is what bounds a slow node.

### An agent turn's dry-run reply

Declare the reply `--dry-run` hands back on the model the turn returns:

```python
from workhorse.pyflow import dry_run

@dry_run(status="done")
class ImplResult(BaseModel):
    status: Literal["done", "blocked"]
    notes: str = ""
```

Every turn that returns `ImplResult` then answers `status="done"` under `--dry-run`. The
decorator validates the reply against the model when the module imports. A stale value
fails the import, not a dry run that happens to reach the turn. The declaration belongs to
the class it decorates, so a subclass does not inherit it.

A turn takes its reply from the first of three places that has one:

1. its prompt stem or inline label in `Registry.stub_agents({...})`,
2. the `@dry_run` reply on its return model,
3. a blank instance of its return model.

The table entry overrides the model. Use it for one turn that must answer differently from
the other turns sharing its model, or for a turn that returns a `str`, which no decorator
can carry. Once a workflow declares a reply either way, a dry run that reaches a fail
terminal exits `1`. A workflow with no declared reply answers every turn blank, so its
fail terminal still exits `0`.

### A node shares the driver's fate

`self.call(node, …)` is an in-process function call — that is what makes a node's spans and
log records land in the run's telemetry at all. The cost is one-directional: a node that
calls `os._exit`, segfaults a C extension or exhausts memory takes the run down with it,
losing the checkpoint write a raised exception would have gone through. Raise; do not exit.

A process a node **backgrounds** is owned by nothing and is reaped when the node ends. A
process that must outlive its node has to be started detached and owned explicitly —
`ostler.qa.stack`'s `ensure_stack` / `teardown_stack` is the parameterised primitive for it.

## No environment — arguments and workflow parameters only

`os.environ`, `os.getenv` and their kin are **prohibited** anywhere under
`src/workhorse_workflows/`. Everything a node or a state needs is an argument, or a field
on the `Workflow` subclass (settable with `--param`). `make check-no-env` enforces it, as
its own target from the repo root. What that target runs is
**[scripts/check_no_env.py](scripts/check_no_env.py)**, installed beside this skill so the
rule travels with the guard; point it at another workflow repo by declaring that repo's
package under `[check-no-env]` in its `.agent-checks.toml`.

The reason is the checkpoint. A run's inputs are recorded there, so a resume days later on
another machine replays what the run actually started with; a value read from the
environment is in no checkpoint, so a resume silently takes a *different* one and nothing
in the artifacts says so. It is also absent from the run's telemetry and unreachable from
`--params`, which splits the operator contract across two spellings no test compares.

The **process boundary** is where the environment legitimately lives, and it is outside
this package: `workhorse/cli/run.py` and `workhorse/supervisor.py` translate `$FOO` into
`--params` once, on the way in. That is why `repo_dir` reaches every workflow without any
of them reading `AGENT_REPO_DIR`.

The ambient paths — `repo_dir`, `workspace`, `library_dirs` — are the shape that used to
be an environment read: wanted by every second node, chosen by no state. They are fields,
and `Workflow.injects` (see `coder/shared/paths.AMBIENT`) fills them into any node or sub-flow
declaring a parameter of the same name that was not passed one. A callsite value always
wins; an empty field injects nothing, so the target's own default stands.

```python
# in the Workflow subclass
injects: ClassVar[tuple[str, ...]] = ("repo_dir", "workspace")

# the node just declares what it wants — the callsite says nothing
def collect(logger: Logger, repo_dir: str = "") -> Docs:
    root = kit.find_docs_root(repo_dir)
```

A secret follows the same rule from the other side: it must never become a `--param`, because
params are checkpointed to disk and echoed in logs and telemetry. `kit/credentials.py`
resolves the GitHub token with `saddlebag.secret_value`, from the saddlebag secret that
`workflow.githubTokenSecret` in `agents.yml` names, and never from a variable. A node that
needs a secret asks saddlebag for it there. A token reaches a git subprocess in that
command's own environment, never in `os.environ`. The full rule is in `workflows/README.md`.

## Idempotency, not just determinism

A resume re-enters a state **from the top**, so every node the state already called is
called again. A node must therefore be safe to run twice: create-or-reuse a branch rather
than create, `mkdir(exist_ok=True)`, skip a commit with nothing staged, look for an open PR
before opening one. "It only worked because it ran once" is the defect this contract names.

## Logging and activity

```python
logger.info("Starting with spec_dir=%s", spec_dir)
logger.warning("Skipping %s: no agents.yml", repo_name)
logger.info("gate %s: implementing", gate_id, extra={"activity": True})
```

`extra={"activity": True}` flags a record as *what the run is doing now* — the rendered
message **is** the activity, so it is never written twice. Workflow-level dimensions
(`work_id`, epic, service…) go in the `Workflow.labels()` override instead, not in log text.

## Pipeline — drain a kind of the run's work list

A stage that works through many items of one kind uses `self.pipeline`, not a hand-written loop.

```python
def epics(self) -> Transition:
    return self.pipeline("epic", to=EpicAuthor, n=1) or Continue(None, self.fill_stories)
```

- **Rows.** The run's work list is `self.work_list`. A kind on it is the list of items. Items run one at a time, in chunks of `n`. Nothing runs in parallel.
- **Two targets.** `to` is a `Workflow` subclass or a state of the same workflow. A flow gets one handoff per row, with the row's payload and the extra keywords. A state gets `items: list[WorkItem]`, and its chain must end by continuing into the drain state.
- **Settle on re-entry.** Entering the drain state settles every row of the kind that is still `active` to `done`. A flow target's row settles right after its handoff returns. A row the target moved itself, to `blocked` for example, keeps that verdict.
- **Resume.** The visit a resume lands on leaves active rows alone. The claim re-takes them first, so only the row that was in flight runs again.
- **Lap cap.** Each claim counts a lap. A row claimed more than `laps` times (default 3) is marked `blocked` and not dispatched.
- **Note and requeue.** A row's `note` reaches a flow target that declares a `note` field. `work.requeue(ids, note)` returns rows to pending with zero laps and the note, which is how an operator's answer sends unfinished rows round again.
- **Fill before drain.** A barrier state fills a kind from the source of truth before the drain that empties it. The drain never works from a list that is still growing, and the filler skips ids already on the list.

## Subagents — choose the prompt by the CLI

`self.subagents` says whether the run's agent CLI can spawn subagents. It is `True` for claude, codex and opencode, and `False` for copilot. A dry run answers `False` unless the test's `RunEnv` sets `subagents`.

A turn that wants one subagent per concern keeps two prompt files. The delegated prompt tells the agent to spawn a subagent for each concern and merge their verdicts. The inline prompt judges every concern in one turn. The state picks the file with `self.subagents`, and both return the same output model.

## The diagram reads what you wrote — so write it

`workhorse-<name> dot` draws each state as the chain of steps it runs and labels each
transition with why it is taken. It invents no text: a node bubble is captioned with the
first line of the node's docstring, a prompt bubble with the prompt's `#` title, an edge
with the transition's reason. Leave one out and the diagram shows a bare file name or a
parameter list instead. Three habits, then, on every state you touch:

- **A one-line docstring on every node**, a sentence saying what it produces —
  `"""Rank the pending items by the checker's last verdict."""`.
- **A `# <workflow> — <what this turn does>` title on every prompt**; the part after the
  dash is the caption.
- **A `.because("…")` on every `Continue`, `Await` and `Done`**, under sixty characters,
  taken from the guard above the `return` — `"drain empty: re-run doctor"`, not `"next"`.
  The driver logs it on the transition line, so the run log reads the way the diagram does.

Hold the line with a test in the workflow's own suite: walk `state_graph(Flow).states` and
assert no edge has an empty `reason`. The
mechanics — what a step is, how a handoff is drawn — are in workhorse's `docs/CHECKING.md`
and `docs/AUTHORING.md`.

## Failure routing — commit the evidence, fail red, never publish

A gate that fails must leave the broken work somewhere obvious and stop the run. It must
never fall through to a publishing step (open a PR, merge, deploy, mark an epic done).
In a state machine the shape is:

- have the failing branch call its **own** commit node with an unmistakable message
  (`"author: INCOMPLETE — unwritten stories, do not merge"`), then `raise WorkflowFailed(…)`
  — the partial work stays on the branch, findable, and the run exits non-zero;
- keep the publishing call reachable **only** from the passing branch. In Python the old
  `default:`-swallows-everything hazard becomes an `else:`: an `else` that falls through to
  the happy path turns every unanticipated verdict into a green run. Route the unknown
  verdict to the failure arm, or `raise WorkflowFailed` naming the value you did not expect;
- name the offenders in the node's own returned model (an `errors` field) and, when the doc
  graph owns the fact, as a `doctor` finding too, so the failure is visible from outside.

Deleting the partial artifact is the wrong instinct: work that vanishes on failure is
indistinguishable from work never attempted.

## Dependencies — declare them in the distribution, import at the top, never degrade

There is no `requires:` block. A workflow distribution declares what its nodes need in its
own `[project.dependencies]` (`workflows/pyproject.toml` for `workhorse-workflows`), and
resolving a workflow *name* imports its package — so an unimportable dependency fails at
import, before any node runs, which is where it belongs.

Two rules follow, and they are the whole point:

- **Import at module scope.** No `import` inside a `def`. A declared dependency is
  importable by the time the workflow resolves, so the import cannot usefully fail there.
- **No degradation branch.** Never write `try: import X / except ImportError:` followed by
  emitting a verdict anyway. A node that answers "is this story authored?" with "I couldn't
  load the graph, so — yes" is worse than one that crashes; that shape is what lets a run
  produce empty artifacts and report success.

Catch narrowly around the *work*, not around the import: `except (OSError, ValueError,
RuntimeError, KeyError)` around a graph load that can legitimately fail, with the failure
returned as a **negative** verdict plus its reason. A verdict that could not be computed is
never a pass.

The one accepted `try/except ImportError` is a genuinely optional dependency (PyYAML) —
still at module scope, binding the name to `None`, with every user returning early on
`yaml is None` so a later `yaml.YAMLError` reference cannot raise `NameError`.

## JSONC parsing

VSCode workspace files are JSON with Comments (trailing commas, `//` comments). Parse them
with `load_jsonc()` from `workhorse_workflows.kit` — never `json.loads()` directly. Anything a
node *writes* is strict JSON; only input may be JSONC.

## The shared helpers — `workhorse_workflows.kit`

Everything a node reuses lives in the **workflow** distribution, not the engine: git, GitHub
and workspace resolution, plus `find_repo_root`, `find_docs_root`, `load_json`, `load_jsonc`
and `run_tool`. `run_tool` is the seam for a genuine external CLI — one that is not git,
GitHub or ostler.

**Never shell out to `git` or `gh`.** The helpers wrap GitPython and PyGithub behind seams, so
a node never touches the CLIs while git still runs for **real** under test. Take the repo root
as an **argument** (`kit.find_repo_root(repo_dir)`), never from the environment.

**[references/kit-helpers.md](references/kit-helpers.md)** is the full surface: every function
on `kit.git` / `kit.github` / `kit.workspace`, the idempotent branch and commit recipes, why
`push_branch` verifies the remote head advanced, which module to patch (the defining
submodule, not the `kit` facade), and the working-directory rule. Read it before writing a
node that touches a repo, a branch, a PR or a workspace file.

## Planning graph (ostler) — the in-process `ostler` API, never subprocess

Don't shell out to the `ostler` CLI — no `subprocess.run(["ostler", …])`, no
`kit.run_tool(["ostler", …])`, no local helper scraping `--json` out of stdout. `ostler` is a
dependency of the workflow distribution, so a node commands the planning graph **as a library**
through the `Ostler` facade, which returns plain Python objects and which an in-process test
fakes by patching the class.

**[references/ostler-api.md](references/ostler-api.md)** carries the branch: the calls a node
makes, the snapshot-and-invalidation semantics that decide what a read sees after a mutation,
why a raise means unreadable while `[]` means empty, and the lazy-imported QA / artifact /
edit subsystems the coder's QA nodes route through. Read it when a node reads or mutates
anything under `docs/`.

## Changing code a live run is already holding

A run imported the workflow package when it started; editing the file on disk changes
nothing for it. Committing a fix is therefore not the last step — every run still in
flight keeps executing the code you just replaced, for as long as it has left. Reload
each one in place instead of restarting it: a restart costs the in-flight turn and opens
a second run generation groom reads as a failure.

The procedure — finding the live runs through groom, checking the run resolves your
source tree rather than a wheel, the `--at-boundary` and `--core` choices, and how to
confirm the reload landed — is [[workhorse-operate]]. It is the operator's skill, so it
loads on the ask and not on this file.

## Testing — substitute, don't patch

A node test substitutes its collaborators and never patches them. The rules and the shapes are in [references/testing.md](references/testing.md). Open it before you write a node test.
