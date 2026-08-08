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
| `--cli {claude,codex,copilot,cline,opencode}` | Which agent CLI drives the run (default `claude`; or `AGENT_CLI`) |
| `--params '<json>'` / `--params-file <path>` | Set the workflow's declared inputs on a fresh start |
| `--dry-run` | Check the workflow and exit without running a node (see [Checking a workflow before you run it](#checking-a-workflow-before-you-run-it---dry-run)) |
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

The three subcommands each command carries are `run`, [`dot`](#diagramming-a-workflow-workhorse-name-dot)
and `version` — what the author of a workflow needs: run it, draw it, say which engine
version drew it.

A workflow's node functions run under workhorse's own interpreter, so a tool they import
must live in *that* environment (`pipx inject workhorse-agent ostler`), not merely on
`PATH`.

The skill and prompt *content* those prompts reference is separate, and separately
configured — see [Initial setup](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/BACKENDS.md#initial-setup).

The skill and prompt references its prompts make are checked in the same breath. A
`{{ instruction_ref("story-docs") }}` that resolves against nothing does not fail — it
renders the sentence `generated story-docs instruction file when installed` into a live
agent prompt, and the agent is left to find the skill itself. Before the first state,
workhorse parses the workflow's `prompts/**/*.md`, resolves every constant reference
against the loaded context manifest, and prints the ones that will not resolve, with the
fix (add them to the repo's `agents.yml` selection and re-run `make agent-install`). It is
a warning, not an error: the run is degraded, not impossible. A run carrying **no**
manifest at all (`hello-world`, most tests) is skipped — there, unresolved is the normal
state. References built from a computed argument can't be seen statically; those log a
`[template] ⚠` line when they render instead.

Only *required* references are reported. A prompt that enumerates the skills for every
stack a workflow has ever met is naming a menu, not a dependency — a Go repo must not be
told to read a Flutter skill, and must not fail preflight for not having one. Three ways
to say so:

```jinja
{# by capability: whichever skills carry ALL of these tags, whatever they are called #}
{%- set web_tests = find_by_tags("web", "tests") %}
{%- if web_tests %}
- How this repo writes web tests: {{ web_tests }}
{%- endif %}

{# plural: render whichever of these the repo installed, drop the rest #}
{%- set web = instruction_refs("react-router", "react-router-qa", "flutter", "pulumi") %}
{%- if web %}
- Instruction files for this layer: {{ web }}
{%- endif %}

{# or guard a whole branch on one skill #}
{% if isUsingInstruction("flutter") %}{{ instruction_ref("flutter-testing") }}{% endif %}
```

`find_by_tags(...)` takes **tags**, not names: each installed skill's `tags:` front matter
rides the manifest, and a skill matches only if it carries every tag asked for (AND — a
second tag narrows). It renders the matches the same way `instruction_refs` renders its
survivors, sorted so a regenerated manifest doesn't reshuffle the prompt, and returns the
**empty string** when nothing matches or nothing is asked. Asking is what a workflow that
ships to unknown repos can honestly do: the name of the skill teaching a subject is the
repo's business, the subject is not. Its arguments are never preflight findings either —
they name a capability, not a file, so "absent" is an answer rather than a defect.

`instruction_refs(...)` (aliases `instruction_files`/`skill_files`, and `prompt_refs`/
`prompt_files` for prompts) takes any number of names — or one list — resolves each,
renders the survivors as a backtick-quoted comma-separated list deduplicated by path, and
returns the **empty string** when none resolve, so `{% if %}` can drop the sentence rather
than leave a dangling "e.g.". Its arguments are never preflight findings, and neither are
references inside an `isUsingInstruction` branch (its `{% else %}` and `{% elif %}` are
judged on their own, since they render precisely when the guard did not hold).

`skill_load_ref("name", fallback_path)` is the imperative one: where `instruction_ref`
yields a path for a prompt to cite, this yields the instruction that *loads* the skill in
whatever harness is running — a `/slash-command` on Claude Code, `Read \`<path>\` and
follow its instructions` elsewhere. Both spellings are derived from the one resolved
path, because farrier installs a skill under the consuming repo's prefix
(`ostler-documentation` → `<repo>-ostler-documentation`) and the registered command is
that installed name, not the one the prompt asked for. Its first argument **is** a
required reference and is preflighted like any other; the second is only where an
uninstalled skill would have lived, and is never checked.

> **Running unattended in a container?** The source repo ships a Docker harness
> (image + compose) for fully isolated, week-long runs with credential seeding
> and persistent volumes. It is *not* part of the PyPI package — see
> [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).

## Checking a workflow before you run it (`--dry-run`)

`--dry-run` checks a workflow and exits without running a node — `0` when it is
clean, `1` on the first problem, so CI can read it. The failure it exists to catch
is a typo found at hour 30 of an unattended run.

```bash
workhorse-coder run --dry-run
```

It turns the skill/prompt reference warning described above into an exit code, and
then does two complementary things.
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

## Diagramming a workflow (`workhorse-<name> dot`)

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

## Choosing the agent CLI backend

The controller drives one agent CLI per run, behind a backend port
(`workhorse/runner/backends/`, one module per CLI). The CLI is chosen **per-run**; the
*model* is per-node:

```bash
workhorse-<name> run                      # claude (default)
workhorse-<name> run --cli codex          # or copilot, cline, opencode
# Equivalently, set the AGENT_CLI={claude,codex,copilot,cline,opencode} env var.
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

The full reference — the `power` and `[default.<backend>]` tables, per-harness
environment variables, where the config file lives and how its schema version keeps
workhorse and farrier in step, initial setup, codex config profiles, and running
OpenRouter models on `cline`/`opencode` (where pinning the upstream endpoint is the
largest cost lever on a long run) — is in
[docs/BACKENDS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/BACKENDS.md).
The resilience and timeout knobs are env vars, documented in
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

## Resuming and run identity

The controller is **auto-resume-in-place** by default. Each `(workflow, run-id)`
pair maps to one stable run dir (`<workflow>-<run-id>`). When you don't pass
`--run-id`, the id defaults to a short **digest of `--params`** (e.g.
`okf-builder-p1c7e4b2a`), or to `default` when the run carries no params. This keeps
the resume contract while stopping distinct targets from colliding: a build for
`{service: report}` and one for `{service: api}` get different dirs automatically, so
the second never silently resumes the first (and drops its `--params`). Re-running
the *same* params re-derives the *same* id, so a crash/reboot/plain re-run still
resumes the existing checkpoint — which is why it's a digest, not a random id.
On start the controller looks for a checkpoint there:

- **No checkpoint** → start fresh from the workflow's `start` state in that dir, which
  is **emptied first**. A finished run leaves its per-node subdirectories behind, and
  since the id is derived from the params they are sitting in the next run's dir under
  the next run's name — a post-mortem then reads a clean run as having entered nodes it
  never reached, with nothing on disk to catch the misreading. **Copy the directory
  aside before relaunching if you want the previous run's artifacts**; an archive left
  *inside* `runs/` would be counted as a run by anything aggregating the tree.
- **Checkpoint present** → resume from the checkpointed state, restoring the frozen
  inputs, `ctx` and the state's parameters. Resume re-enters that state from the top,
  which is why idempotency — not merely determinism — is the contract a state body
  owes; see [Checkpoints and renaming](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#checkpoints-and-renaming).

This is what lets an unattended run survive a crash or reboot: relaunching the
same workflow continues where it left off. To start over, delete the run dir. To
keep independent runs of the same workflow side by side, pass distinct run ids.

**Ctrl-C is recorded, not silent.** An interrupt pauses the run the same way a crash
does — `terminal` stays `null` so the next launch resumes in place — but it also
stamps `run.json` with `interrupted_at`/`error` and appends an `error` event for the
node that was in flight. Without that, a stopped run and a run wedged in a node are
byte-identical on disk: the node's `enter` event has no `done` either way, and the
only record that a human hit Ctrl-C lives in the agent CLI's session transcript. The
stamp is cleared by the resume that follows it.

Controller flags (passed to `workhorse`; `--resume-*` are manual overrides
of the auto behavior above):

| Flag | Purpose |
|---|---|
| `--run-id <id>` | Name the stable run dir (`<workflow>-<id>`); default: a digest of `--params`, else `default` |
| `--resume-run <path-or-name>` | Resume a specific run dir from its checkpoint |
| `--resume-latest` | Resume the most recent unfinished run under `--runs-dir` |
| `--params '<json>'` / `--params-file <path>` | Set the workflow's declared inputs on a fresh start (also keys the default run dir) |

"Survives reboot" therefore covers both the *work products* (commits, sessions,
artifacts) **and** position in the machine — an interrupted run auto-resumes mid-flight.

## Run artifacts

Each workflow execution writes a timestamped directory:

```
runs/
└── <workflow-name>-<timestamp>-<id>/
    ├── run.json                  # start/end time, terminal state, interrupt stamp
    ├── context.json              # final context snapshot
    ├── sessions.jsonl            # {node, session_id} per agent turn — map a node to its CLI session
    └── <step-id>/
        ├── prompt.md             # rendered prompt, written before agent invocation
        ├── output.json           # extracted JSON outputs
        └── context_after.json    # context state after this step
```

Artifacts are written under `--runs-dir` (default `<cwd>/.agents/runs`). Before
each agent turn, workhorse writes the rendered `prompt.md` and logs only that path
so failed or interrupted nodes remain inspectable without dumping variables. The
Docker harness redirects artifacts to a persistent volume instead — see
[docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).

`prompt.md` and `output.json` capture a step's *input* and *final* answer, not the
agent's step-by-step reasoning and tool calls in between — that transcript lives in
the agent CLI's own session store, keyed by session id. `sessions.jsonl` records the
`node → session_id` map for every agent turn so you can recover it afterward (e.g.
`opencode export <session_id>`). It is an append-only manifest because the live
`.session_id` file holds only the *current* node's session; a node can appear more
than once (loop revisits, compact/reframe within a node), so the mapping is
`node → sessions` and consumers dedup on read. With telemetry on the same
session id is also set as the `session.id` attribute on the agent-turn span.

## Telemetry (automatic when a collector is reachable)

For away-from-keyboard monitoring of long runs, workhorse streams OpenTelemetry spans,
metrics and log records to a local OTLP collector — by default
[`groom`](https://github.com/GabrielCpp/stablemate/tree/main/groom), which
stores them in SQLite and pages you (ntfy/webhook + browser) on stall/stuck/churn:

```bash
pip install 'workhorse-agent[otel]'
groom serve                                                # now every run is observed
```

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
renders. Control flow is ordinary Python — `if`, `for`, a counter that is just a counter —
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
