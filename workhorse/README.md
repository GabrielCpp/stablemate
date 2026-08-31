# workhorse

[![PyPI](https://img.shields.io/pypi/v/workhorse-agent.svg)](https://pypi.org/project/workhorse-agent/)

**A fail-soft runner for agent workflows written as Python state machines — drives
an agent CLI (Claude, Codex, Copilot, Cline or OpenCode) unattended for days.**

A workflow is a Python package: its states are methods that return the next state,
its nodes are plain functions. `workhorse` drives the machine, renders Jinja2
prompts, invokes the agent CLI, validates JSON replies into typed models,
checkpoints after every transition, and writes run artifacts.

> The PyPI distribution is **`workhorse-agent`**; the import package and CLI
> command are both `workhorse`.

## Why

`workhorse` exists to run long, multi-step agent workflows **unattended** — the
design target is a single run that survives for a week without a human babysitting
it. That goal drives the two defining properties of the tool:

- **Resilience is the default, not a mode.** A single flaky node (an empty agent
  response, a rate limit, a spending cap, an unparseable output) must never crash
  the whole run. The runner retries transient failures, reframes the prompt, and
  finally defaults a turn's outputs so the machine advances to its next state
  rather than aborting. See [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md) for the full recovery
  ladder and its tuning knobs.
- **Reproducibility and resume.** Every step is recorded as a run artifact and
  the driver checkpoints after each transition, so a run resumes from exactly where
  it left off after a crash or reboot.

It is repository-agnostic: the same workflow runs against any repo a workflow's
`setup.sh` chooses to clone. A containerized harness for fully isolated,
unattended runs lives in the source repo — see [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md)
(not shipped in the PyPI package).

### Why a workflow is Python and not a config file

Workhorse used to read workflows from a declarative `workflow.yaml` — a graph of
typed nodes with `next:` edges. That front-end is deleted, and since every other
page here states the consequence rather than the reason, the reason lives here.

**The schema was not failing at expressing graphs. It was failing at the two
things a graph does not model: values and loops.** A constant had to be declared
as a string and then kept in sync with its use sites by comment, because a branch
condition could not be a template expression. A bounded retry — `for _ in
range(3)` — needed four extra nodes and three scripts to emulate a counter. And
every value crossing a node boundary was a Jinja string, so an `int` arrived
stringified and nothing between two nodes was checkable. Those workarounds do not
shrink with practice; they grow with the workflow. The four workflows in this
repo reached ~8,000 lines of YAML, of which one was 4,366.

In Python all three stop being problems, because they were never workflow
problems: a constant is a constant, a loop is a `for`, and a value crossing a
transition is a typed model that fails at the boundary that produced it.

**The second reason is dependency isolation, and it may be the bigger one.** A
`script:` node imported its libraries from *workhorse's own interpreter*, so
using a workflow meant injecting that workflow's dependencies into the runner's
environment. A workflow is now an ordinary distribution: its dependencies are
`[project.dependencies]`, resolved by `pip`/`uv` at install time, and workhorse
is merely one of them.

What this deliberately gives up is a complete static graph. Native control flow,
a fully declarative graph, and a single source of truth are a pick-two — a
declarative graph can only stay honest if it is the only description of the flow,
and then it cannot use the host language. Splitting at the **state** boundary buys
most of the third back: transitions between states are still recoverable as a
diagram (`workhorse-<name> dot` draws it), while the interior of a state is
opaque — and the interior of a state is the part nobody wanted to read as a
diagram anyway.

> **Holding a `workflow.yaml`?** [docs/WORKFLOW.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/WORKFLOW.md)
> maps every construct in the retired schema to what replaces it, names the three
> that have no counterpart, and lists what did not change at all.

## Install

```bash
pip install workhorse-agent     # or: uv add workhorse-agent
```

This installs the **library**, not a command: workhorse drives no executable of its
own. What you run is the console script the *workflow's* distribution binds — see
[Running a workflow](#running-a-workflow-workhorse-name-run) — so in practice you
install that distribution, and workhorse comes along as one of its dependencies.

You also need the agent CLI you intend to
drive on your `PATH` and authenticated — by default the [Claude
CLI](https://docs.claude.com/en/docs/claude-code) (`claude`), authenticated via a
Claude subscription or `claude setup-token`. `codex`, `copilot`, `cline` and
`opencode` are also supported (see
[Choosing the agent CLI backend](#choosing-the-agent-cli-backend)).

Requires Python ≥ 3.12.

## Quick start

Install a workflow distribution and run one of the commands it brings. You need the
agent CLI (`claude` by default) installed and authenticated:

```bash
workhorse-hello-world run
workhorse-coder run qa --params '{"story":"CASE-1234","target_env":"dev"}'
```

Key flags (run `workhorse-<name> --help` for the full list):

| Flag | Purpose |
|---|---|
| `--runs-dir <dir>` | Where to write run artifacts (default: `<cwd>/.agents/runs`) |
| `--run-id <id>` | Name the stable run dir (`<workflow>-<id>`); default: a digest of `--params`, else `default` |
| `--cli {claude,codex,copilot,cline,opencode}` | Which agent CLI drives the run (or `AGENT_CLI`, else the config's `default_cli`, else `claude`) |
| `--profile <name>` | Which named `[profiles.<name>]` set of models this run uses (see [Naming a set of models](#naming-a-set-of-models-profiles)) |
| `--config <path>` | Use this config file instead of the discovered one, for this run and everything it spawns |
| `--params '<json>'` / `--params-file <path>` | Set the workflow's declared inputs on a fresh start |
| `--dry-run` | Check the workflow and exit without running a node (see [Checking and diagramming a workflow](#checking-and-diagramming-a-workflow)) |
| `--resume-run <path-or-id>` / `--resume-latest` | Manually resume a checkpointed run |

### Running a workflow (`workhorse-<name> run`)

Every workflow brings its own command. `run` is the default subcommand, so it can be
left out:

```bash
workhorse-research run                              # the workflow's entry flow
workhorse-research run qa                           # one flow standalone
workhorse-research run qa --params '{"k":"v"}'      # with param overrides
workhorse-research qa                               # same as `run qa`
```

There is **no `workhorse` executable and no resolution by name.** The command is bound
inside the workflow's own distribution, which hands its `Registry` straight to the CLI:

```python
# myworkflows/research/workflow.py
main = console_script(workflow.entry_point(Research))
```

```toml
[project.scripts]
workhorse-research = "myworkflows.research.workflow:main"
```

So the workflow that runs is the one whose command you typed — nothing is looked up, and
a name that has no script simply has no command, which you notice at install time rather
than at resolution time. The script must point at what `console_script(...)` **returns**
(`[project.scripts]` targets are called after import, so a module-level `main = …` is the
shape).

The package must be installed **unpacked** (any pip/uv wheel is): the prompt renderer is
a filesystem template loader rooted at the workflow's own directory, so a zip-imported
package is refused at startup rather than failing later as a missing template.

The five subcommands each command carries are `run`, [`dot`](#checking-and-diagramming-a-workflow),
[`control`](#reaching-a-run-that-is-already-going), `inbox` and `version` — what the operator of a workflow
needs: run it, draw it, steer the live process, read or answer the messages a run left at
its operator gates, and say which engine version did it.

A workflow's node functions run under workhorse's own interpreter, so a tool they import
must live in *that* environment (`pipx inject workhorse-agent ostler`), not merely on
`PATH`.

The skill and prompt *content* those prompts reference is separate, and separately
configured — see [Initial setup](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/BACKENDS.md#initial-setup).

The skill and prompt references those prompts make are checked before the first state, and
the ones that will not resolve are printed with the fix. It is a warning, not an error — an
unresolved reference degrades a prompt rather than stopping the run — and `--dry-run` is
what turns it into an exit code. Which references count as *required*, and the Jinja
helpers (`find_by_tags`, `instruction_refs`, `skill_load_ref`) a workflow shipping to
unknown repos uses to ask for a skill without demanding it, are in
[docs/CHECKING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/CHECKING.md).

> **Running unattended in a container?** The source repo ships a Docker harness
> (image + compose) for fully isolated, week-long runs with credential seeding
> and persistent volumes. It is *not* part of the PyPI package — see
> [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).

## Checking and diagramming a workflow

`--dry-run` checks a workflow and exits without running a node — `0` when it is clean, `1`
on the first problem, so CI can read it. The failure it exists to catch is a typo found at
hour 30 of an unattended run. `dot` renders the same workflow to
[Graphviz](https://graphviz.org) DOT, read off the states rather than a separate diagram,
so it cannot go stale.

```bash
workhorse-coder run --dry-run
workhorse-coder dot -o wf.dot && dot -Tsvg wf.dot -o wf.svg   # render (needs graphviz)
```

The dry run does a static pass over the states' source — every rendered prompt path exists,
every state is reachable, something can return `Done`, no transition names a non-state —
and then drives the machine for real over a *substituted* node index, where every node body
and agent reply is a stand-in. What each half catches, what a fail terminal means with and
without `stub_agents({...})`, the `dry-run` run dir, and `dot`'s flags and rendering rules
are in [docs/CHECKING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/CHECKING.md).

## Choosing the agent CLI backend

The controller drives one agent CLI per run, behind a backend port
(`workhorse/runner/backends/`, one module per CLI). The CLI is chosen **per-run**; the
*model* is per-node:

```bash
workhorse-<name> run                      # the configured default_cli, else claude
workhorse-<name> run --cli codex          # or copilot, cline, opencode
# Equivalently, set the AGENT_CLI={claude,codex,copilot,cline,opencode} env var.
```

The unnamed case is configurable, so a machine set up for one CLI does not have to
name it on every run — put `default_cli` in the shared config (see
[BACKENDS.md](docs/BACKENDS.md#choosing-the-agent-cli-backend)):

```toml
default_cli = "opencode"
```

| Backend | CLI | Default model | In-place compaction |
|---|---|---|---|
| `claude` | `claude -p` (stream-json) | `sonnet` | yes (`/compact`) |
| `codex` | `codex exec --json` | CLI default | no — ladder reframes on overflow |
| `copilot` | `copilot -p --output-format json` | CLI default | no — ladder reframes on overflow |
| `cline` | `cline --json` | — (node names it) | no — ladder reframes on overflow |
| `opencode` | `opencode run --format json` | — (node names it) | no — ladder reframes on overflow |

JSONL provider error events and logs that identify a transient failure are aborted
immediately and retried by workhorse's bounded backoff instead of being left to a CLI's
opaque internal retry loop.

A workflow does not name a model. An agent turn asks for an abstract `power` tier
(`high` / `medium` / `low`) and your user-wide config — one file shared with `farrier`,
at `~/.config/stablemate/config.toml` — maps that tier to a concrete model and effort for
the active backend. Turns with no `power=`, and tiers with no mapping, fall through to
`AGENT_MODEL`, then to a per-backend `[default.<backend>]` table, then to the harness's
own default:

```toml
[power.high.claude]
model = "opus"
effort = "high"
```

### Naming a set of models (profiles)

Editing those tables moves **every** run on the machine, including the six-day one already
going. A `[profiles.<name>]` table instead holds its own `power`, `default` and
`default_cli` under one name, picked per run with `--profile cheap` (or a whole other file
with `--config ./experiment.toml`). A profile **replaces** the top-level tables rather than
layering over them, and the one a run chose is recorded in its `run.json` and stamped on its
root span as `workhorse.profile` — so a flagless `--resume-run` re-applies the same set, and
a finished run can still say which models it bought.

The full reference — the `power` and `[default.<backend>]` tables, per-harness
environment variables, where the config file lives and how its schema version keeps
workhorse and farrier in step, initial setup, codex config profiles, and running
OpenRouter models on `cline`/`opencode` (where pinning the upstream endpoint is the
largest cost lever on a long run), and the full `[profiles.<name>]` reference — is in
[docs/BACKENDS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/BACKENDS.md).
The resilience and timeout knobs are env vars, documented in
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

## Resuming and run identity

The controller is **auto-resume-in-place** by default. Each `(workflow, run-id)` pair maps
to one stable run dir (`<workflow>-<run-id>`), and when you don't pass `--run-id` the id
defaults to a short **digest of `--params`** (e.g. `okf-builder-p1c7e4b2a`). Re-running the
same params re-derives the same id, so a crash, a reboot or a plain re-run resumes the
existing checkpoint — which is what lets an unattended run survive either. Distinct params
get distinct dirs, so one target never silently resumes another's checkpoint and drops its
own. To start over, delete the run dir; to keep independent runs side by side, pass
distinct `--run-id`s.

Ctrl-C is recorded rather than silent: the run pauses the way a crash does *and* stamps
`run.json`, so a stopped run and a wedged one are not byte-identical on disk.

The resume branches in full, the `--resume-run` / `--resume-latest` / `--params` flag
table, and why a fresh start empties the dir first are in
[docs/RUNS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/RUNS.md).

## Reaching a run that is already going

A healthy run can be spending real money on a flow you have already fixed on disk. It does
not need stopping — it needs the pushed code. A control channel on the run dir carries
commands into the live process, answered even from inside a multi-day cap sleep:

```bash
workhorse-coder control --run <id> reload                 # cut the turn, re-enter on the pushed code
workhorse-coder control --run <id> reload --at-boundary   # let the turn land first
workhorse-coder control --run <id> reload --core          # …and replace workhorse itself
workhorse-coder control --run <id> status                 # is this process still serving this run dir
workhorse-coder control --run <id> questions              # what is this run asking an operator?
workhorse-coder control --run <id> answer --text "go"     # answer the gate it is parked on
workhorse-coder control --run <id> switch-cli claude      # move it onto another agent CLI
workhorse-coder control --run <id> switch-profile cheap   # move it onto another set of models
```

A reload cuts the turn within about a second, closes its span with the usage it really
accrued (stamped `workhorse.cut=reload`, so groom does not read it as churn), spends no
recovery budget, and re-enters the checkpoint the state wrote on entry — **same process, same
pid, same root span, same run dir, same wall-clock budget.** Not a new run. `--core` is the
one that costs a process image, because workhorse's own modules are on the frame doing the
reload.

Full mechanics — what `--at-boundary` is for, which packages a reload replaces and which it
deliberately leaves alone, what the spans are stamped with, and what each sibling command
does to a run mid-flight — are in [docs/RELOAD.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/RELOAD.md).

## Run artifacts

Each run writes a directory under `--runs-dir` (default `<cwd>/.agents/runs`), holding
`run.json` and the final `context.json`, the `checkpoint.json` a resume restarts from and
the `events.jsonl` log of every state transition, one `<step-id>/` per step with the
rendered `prompt.md` and extracted `output.json`, a `turns/` dir keeping every *earlier*
visit a looping node overwrote, `sessions.jsonl` mapping each turn to its agent-CLI
session, and `transcripts/` capturing the turns themselves — because the CLI's own session
store lives on one host and is pruned whenever it likes.

```
runs/<workflow>-<run-id>/{run.json,launch.json,checkpoint.json,context.json,events.jsonl,sessions.jsonl,turns/,transcripts/,<step-id>/}
```

`launch.json` is the one written for whoever outlives the process. A run killed outright —
OOM, a sweep, a hard crash — cannot report its own death, so something outside has to notice
and act, and until this file the directory said everything about the run except how to start
it again. It holds **two** argvs, and the difference is load-bearing:

- `resume_argv` is the command. Run it from the recorded `cwd`. Because a resume lands on the
  stable run dir in place, that is the whole of what a supervisor has to do.
- `argv` is forensics — what this process was actually exec'd with — and must **never** be
  executed. It can carry `--no-cache`, which deletes the run directory before starting, and a
  `--params-file` that has since moved on from what the checkpoint holds. Replaying it is not
  a resume; it is how the run gets lost.

`container: true` means every path in the record is namespace-local, so a host-side reader
must refuse it rather than re-spawn coordinates that mean something else outside. The
environment is deliberately not recorded: it is read at the process boundary and would put
secrets on disk.

The full tree, what `prompt.md` does and does not capture, how a transcript capture records
which of its two sources it came from, and the `WORKHORSE_CAPTURE_TRANSCRIPTS` /
`WORKHORSE_TRANSCRIPT_MAX_BYTES` bounds are in
[docs/RUNS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/RUNS.md).
The Docker harness redirects artifacts to a persistent volume instead — see
[docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).

## Telemetry (automatic when a collector is reachable)

For away-from-keyboard monitoring of long runs, workhorse streams OpenTelemetry spans,
metrics and log records to a local OTLP collector — by default
[`groom`](https://github.com/GabrielCpp/stablemate/tree/main/groom), which
stores them in SQLite and pages you (ntfy/webhook + browser) on stall/stuck/churn:

```bash
groom serve                                                # now every run is observed
```

The OTel SDK is a **required** dependency, so any install of workhorse can export. It used
to be an `otel` extra, and an install that skipped it produced not "a run without
telemetry" but an *invisible* run: telemetry fails soft, so the exporter was absent
silently and the dashboard showed nothing, which reads exactly like a dead run.

Live gauges distinguish an open agent turn, an explicit operator/cap/retry wait, and
ordinary deterministic node work. Turn idle and elapsed values are cleared when the turn
closes, so a later operator wait cannot inherit stale evidence that an agent is streaming.

**Enablement is auto by default.** With `WORKHORSE_OTEL` unset, `start_run` opens one
short TCP connection to the endpoint and enables telemetry only if something answers — so
a machine running a collector gets spans with no env var, and one without stays a complete
no-op. `WORKHORSE_OTEL=1` forces it on, `0` forces it off. That is the default because the
runs most worth observing are the unattended week-long ones, which are exactly the runs
nobody remembers to export a variable before launching. Auto stays off inside a test
process regardless of the probe — a suite is not a run anyone revisits, and left on it
buries the ones that are.

What is emitted, how turn spans are normalized so cost and tokens are comparable across
harnesses, the cap-wait heartbeat that distinguishes a spending-cap sleep from a hang, and
how to tag spans with your own unit of work are in
[docs/TELEMETRY.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/TELEMETRY.md).
There is also a wall-clock ceiling, `WORKHORSE_MAX_RUNTIME_S` — see
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

## Repository isolation

`workhorse` is repository-agnostic — it never assumes a particular repo or working
tree. If a workflow needs to operate on source code (read, edit, build, test),
include a `setup.sh` script in the workflow directory. It runs from the first state
and clones the required repositories to a known path. This keeps the workflow
reproducible and lets the agent work from a clean, versioned checkout rather than
a host working tree. See any workflow's `scripts/setup.sh` for an example. (The
Docker harness builds on this to give each run a fully isolated, throwaway clone —
see [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).)

## Writing a workflow

A workflow is a Python package: `workflow.py` holds the `Registry` and the `Workflow`
subclasses whose methods are its **states**, `nodes.py` holds the `@blueprint.node`
functions that are its **nodes**, and `prompts/` holds the Jinja2 templates an agent turn
renders. Once a workflow grows more than one machine, each one takes a directory of its
own — `dev/flow.py` beside the `nodes/` and `prompts/` only it renders — `workflow.py`
shrinks to the `Registry` alone, and prompt paths are written from the package root down
(`"dev/prompts/implement-plan.md"`), which is what `Registry(name, package=__package__)`
declares. Control flow is ordinary Python — `if`, `for`, a counter that is just a counter —
and each state returns the next one:

```python
class Build(Workflow):
    subject: str                                   # inputs — filled from --params

    def start(self):
        reading = self.call(measure, self.subject)          # a node
        return Continue(None, self.review, count=reading.count)

    def review(self, count: int):                  # state parameters — one hop only
        verdict = self.agent("prompts/review.md", returns=Verdict, args={"n": count})
        if verdict.ok:
            return Done(verdict)
        return Continue(None, self.review, count=count + 1)
```

An agent prompt must output JSON matching the model its turn declared in `returns=`, and
— because runs go unattended for days — a state must be ready for a reply whose fields
came back empty: after transient retries and reframing, the runner defaults a turn's
declared outputs and lets the machine advance rather than crashing the run.

The authoring reference — the package layout, the worked example end to end, the three
tiers of state and why there is no fourth, where a turn runs (`cwd` / `add_dirs`), the
transition table, checkpoints and the `aliases=` that survive a rename, the node index
that tests substitute through instead of patching, and the `labels()` that tell a
collector what a run is working on — is in
[docs/AUTHORING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md).

### Measuring something outside an agent turn

A benchmark, a training run, an evaluation sweep — anything whose value is a *number* —
does not belong inside an agent turn, whose budget is a budget for thinking and which
kills and re-enters a command that outruns it. `workhorse.job` submits such a command
detached, under a supervisor that outlives the node, and records what it cost in a file
the command itself cannot write: exit code, peak RSS, wall time, kill reason, and the
containment tier the machine actually delivered. The workflow parks on an `Await` and a
later state classifies the two artifacts with no model call.

The manifest keys, the three containment tiers, why time is advisory while memory is hard,
and how a job is polled, adopted on resume and killed are in
[docs/JOBS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/JOBS.md).

## Development

Working on the controller itself — not on a workflow — starts from a clone of the
[stablemate](https://github.com/GabrielCpp/stablemate) repo rather than a PyPI install.
`make help` lists the tasks; `make test` runs the suite, which is dependency-free (each
file in `tests/` also runs standalone under `uv run python tests/test_x.py`).

The project layout, how the driver's loop works, why every agent turn gets a clean
session, where to put a test and which of the two styles it is, where docs go, and the
container build are in
[docs/DEVELOPMENT.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DEVELOPMENT.md).
The Docker harness for isolated unattended runs — not shipped in the PyPI package — is in
[docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).
