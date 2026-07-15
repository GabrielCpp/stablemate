# workhorse

[![PyPI](https://img.shields.io/pypi/v/workhorse-agent.svg)](https://pypi.org/project/workhorse-agent/)

**A fail-soft runner for YAML-defined agent workflows — drives an agent CLI
(Claude, Codex, or Copilot) through a workflow graph unattended for days.**

A workflow is a graph of `agent`, `script`, and `branch` nodes. `workhorse` walks
the graph, renders Jinja2 prompts, invokes the agent CLI or shell scripts,
extracts JSON outputs, checkpoints after every node, and writes run artifacts.

> The PyPI distribution is **`workhorse-agent`**; the import package and CLI
> command are both `workhorse`.

## Why

`workhorse` exists to run long, multi-step agent workflows **unattended** — the
design target is a single run that survives for a week without a human babysitting
it. That goal drives the two defining properties of the tool:

- **Resilience is the default, not a mode.** A single flaky node (an empty agent
  response, a rate limit, a spending cap, an unparseable output) must never crash
  the whole run. The runner retries transient failures, reframes the prompt, and
  finally defaults a node's outputs so the graph advances to its `next` rather
  than aborting. See [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md) for the full recovery
  ladder and its tuning knobs.
- **Reproducibility and resume.** Every step is recorded as a run artifact and
  the graph checkpoints after each node, so a run resumes from exactly where it
  left off after a crash or reboot.

It is repository-agnostic: the same workflow runs against any repo a workflow's
`setup.sh` chooses to clone. A containerized harness for fully isolated,
unattended runs lives in the source repo — see [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md)
(not shipped in the PyPI package).

## Install

```bash
pip install workhorse-agent     # or: uv add workhorse-agent
```

This installs the `workhorse` command. You also need the agent CLI you intend to
drive on your `PATH` and authenticated — by default the [Claude
CLI](https://docs.claude.com/en/docs/claude-code) (`claude`), authenticated via a
Claude subscription or `claude setup-token`. `codex`, `copilot`, `aider` and
`opencode` are also supported (see
[Choosing the agent CLI backend](#choosing-the-agent-cli-backend)).

Requires Python ≥ 3.12.

## Quick start

Run the `workhorse` command against a workflow directory. You need the agent CLI
(`claude` by default) installed and authenticated:

```bash
# Direct path form
workhorse --workflow ./workflows/hello-world/workflow.yaml

# Named workflow form — resolves from the configured prompt library
workhorse run hello-world
workhorse run coder qa --params '{"story":"CASE-1234","target_env":"dev"}'
```

Key flags (run `workhorse --help` for the full list):

| Flag | Purpose |
|---|---|
| `--workflow <path>` | Path to the `workflow.yaml` to run. Alternatively use the positional form: `workhorse run <name> [<flow>]` |
| `--runs-dir <dir>` | Where to write run artifacts (default: `<workflow-dir>/runs`) |
| `--run-id <id>` | Name the stable run dir (`<workflow>-<id>`); default `default` |
| `--cli {claude,codex,copilot,aider,opencode}` | Which agent CLI drives the run (default `claude`; or `AGENT_CLI`) |
| `--params '<json>'` / `--params-file <path>` | Override workflow `vars` on a fresh start |
| `--resume-run <path-or-id>` / `--resume-latest` | Manually resume a checkpointed run |

### Named workflows (`workhorse run`)

The `run` subcommand resolves a workflow by name from the configured prompt library:

```bash
workhorse run <name>                              # run the workflow's default flow
workhorse run <name> <flow>                       # run a specific flow standalone
workhorse run <name> <flow> --params '{"k":"v"}' # with param overrides
```

Configure the library path once:

```bash
workhorse config set-library ~/path/to/prompt-library
workhorse config set-stablemate ~/path/to/stablemate   # optional: sets CODER_WORKSPACE
```

`--workflow` and the `run` positional form are equivalent — use whichever fits the
context. The prompt library path can also be set via `WORKHORSE_LIBRARY_DIR`.

> **Running unattended in a container?** The source repo ships a Docker harness
> (image + compose) for fully isolated, week-long runs with credential seeding
> and persistent volumes. It is *not* part of the PyPI package — see
> [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).

## Diagramming a workflow (`workhorse dot`)

`workhorse dot` renders a workflow graph to [Graphviz](https://graphviz.org) DOT
straight from its `workflow.yaml`, so the diagram never drifts from the workflow.
Styling is type-based: branch nodes are salmon diamonds, terminals green, `fail`
nodes coral, agent/script nodes plain boxes; branch edges are labeled with their
case / numeric-condition / `default`.

```bash
workhorse dot --workflow ./wf/workflow.yaml            # DOT to stdout
workhorse dot --workflow ./wf/workflow.yaml -o wf.dot  # ...or to a file
dot -Tsvg wf.dot -o wf.svg                             # render (needs graphviz)
```

| Flag | Purpose |
|---|---|
| `--workflow <path>` | Path to the `workflow.yaml` to render (required) |
| `--pin KEY=VALUE` | Pin a branch variable; matching branches collapse to their single resolved edge and the now-unreachable subgraph is pruned. Repeatable. |
| `--leaf NODE` | Render `NODE` as a dead-end (suppress its out-edges) to cut a cross-view bridge not gated by a pinned branch. Repeatable. |
| `--name <id>` | Override the `digraph` identifier (default: sanitized workflow name) |
| `-o, --output <path>` | Write to a file instead of stdout |

A workflow that dispatches on a mode variable encodes several modes in one graph;
`--pin` carves out a single mode's view. For example the coder workflow's two
diagrams are just `--pin mode=epic` and `--pin mode=story --leaf replan_epic`.

## Choosing the agent CLI backend

The controller drives one agent CLI per run, behind a backend facade
(`workhorse/runner/backends.py`). The CLI is chosen **per-run** (the *model* is
still per-node — see below):

```bash
workhorse --workflow ./wf/workflow.yaml                      # claude (default)
workhorse --workflow ./wf/workflow.yaml --cli codex
workhorse --workflow ./wf/workflow.yaml --cli copilot
workhorse --workflow ./wf/workflow.yaml --cli aider          # OpenRouter-native
workhorse --workflow ./wf/workflow.yaml --cli opencode       # OpenRouter-native
# Equivalently, set the AGENT_CLI={claude,codex,copilot,aider,opencode} env var.
```

The backend default model is overridable per run with the `AGENT_MODEL` env var.
Workflows can request an abstract `power` tier per node; your user-wide config maps
that tier to concrete backend model/effort settings. Nodes with no `power:` (and
tiers with no mapping) fall through to `AGENT_MODEL`, then to a per-backend
`[default.<backend>]` config table (see [Node power selection](#node-power-selection)).
If nothing supplies a value, Workhorse leaves model/effort unset and the selected
harness uses its own defaults. The resilience/timeout knobs are env vars too — see
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).
JSONL provider error events and logs that identify a transient failure are aborted
immediately and retried by Workhorse's bounded backoff instead of being left to a
CLI's opaque internal retry loop.

| Backend | CLI | Default model | In-place compaction |
|---|---|---|---|
| `claude` | `claude -p` (stream-json) | `sonnet` | yes (`/compact`) |
| `codex` | `codex exec --json` | CLI default | no — ladder reframes on overflow |
| `copilot` | `copilot -p --output-format json` | CLI default | no — ladder reframes on overflow |
| `aider` | `aider --message` (plain text) | — (node names it) | no — ladder reframes |
| `opencode` | `opencode run --format json` | — (node names it) | no — ladder reframes on overflow |

For running OpenRouter models (e.g. MiMo) on `aider` / `opencode`, see
[OpenRouter models](#openrouter-models--aider-and-opencode) below.

### Node power selection

A node's optional `power:` field is one of `high`, `medium`, or `low`. It is not a
model name; it is resolved through the workhorse config file for the active backend
(see [Config file location](#config-file-location) below):

```yaml
nodes:
  - id: lead_review
    type: agent
    power: high
```

Example config:

```toml
[power.high.claude]
model = "opus"
effort = "high"

[power.medium.claude]
model = "sonnet"
effort = "high"

[power.low.claude]
model = "haiku"
effort = "high"

[power.high.codex]
model = "@gpt-5.5"
effort = "high"

[power.high.opencode]
model = "openai/gpt-5.5"
effort = "high"
```

#### Per-backend default model (`[default.<backend>]`)

Nodes without a `power:` tier (and tiers you left unmapped) would otherwise run on
whatever the harness itself defaults to — for `opencode`/`codex`/`copilot` that is
the CLI's own auto-picked model, which may not be what you want. Pin a per-backend
fallback in the same config file:

```toml
[default.opencode]
model = "openai/gpt-5.5"
effort = "high"
```

Model resolution order per node: `power.<tier>.<backend>` mapping → `AGENT_MODEL` /
`AGENT_CLAUDE_MODEL` env vars → `[default.<backend>]` → the backend's built-in
default (`sonnet` for claude; unset for the others, meaning the harness decides).
Effort resolves as: power mapping → `[default.<backend>]` (no env override exists).

Inspect or set config:

```bash
workhorse config show                        # print all config keys
workhorse config show power.high.claude      # print one value
workhorse config set-library ~/path/to/lib   # set the prompt library path
workhorse config set-stablemate ~/path/to/sm # set the stablemate path
workhorse config list                        # list all config keys (power table friendly)
workhorse config get power.high.claude       # get one key
```

#### Config file location

Workhorse stores its own config at a platform-appropriate path (via
[platformdirs](https://github.com/tox-dev/platformdirs)):

| Platform | Default path |
|---|---|
| macOS | `~/Library/Application Support/workhorse/config.toml` |
| Windows | `%APPDATA%\workhorse\config.toml` |
| Linux | `~/.config/workhorse/config.toml` |

Override the path with `WORKHORSE_CONFIG=/path/to/config.toml`.

#### Initial setup

After installing workhorse for the first time, register your prompt library:

```bash
workhorse config set-library ~/path/to/your/prompt-library
# Optionally, also set the stablemate path (used as CODER_WORKSPACE):
workhorse config set-stablemate ~/path/to/stablemate
```

Then verify:

```bash
workhorse config show
# library_dir=/Users/you/path/to/prompt-library
# stablemate_dir=/Users/you/path/to/stablemate
```

### Codex config profiles (`<profile>@<model-slug>`)

For the `codex` backend, the configured model value selects a
[codex config profile](https://github.com/openai/codex) (from
`~/.codex/config.toml`) — which bundles provider, auth and a pinned model — plus an
optional model override, written as `<profile>[@<model-slug>]`. `@` is the delimiter
because `/` and `:` already appear inside model slugs:

| Configured model value | Resulting codex flags |
|---|---|
| `local` | `--profile local` (the profile pins the model) |
| `openrouter@deepseek/deepseek-chat-v3.1` | `--profile openrouter -m deepseek/deepseek-chat-v3.1` |
| `openrouter@` | `--profile openrouter` |
| `@gpt-5.5` | `-m gpt-5.5` (no profile; falls back to `CODEX_PROFILE`) |
| _(unset)_ | `CODEX_PROFILE` if set, else codex's own default |

`CODEX_PROFILE` is the run-level default when the resolved model has no explicit
profile.

> These codex config profiles live in `~/.codex/config.toml`. Each names a
> `model_provider` (`base_url` + `env_key`) and a model; codex 0.128+ requires
> `wire_api = "responses"`. They are codex-internal, distinct from Workhorse's
> `power` mapping.

## OpenRouter models — `aider` and `opencode`

To run a workflow on an OpenRouter model — e.g. the MiMo-V2.5 experiment — drive
the run with an **OpenRouter-native backend** and map the desired `power` tier to an
`openrouter/<slug>` model for that backend. Both `aider` and `opencode` speak plain
chat-completions, so they reach OpenRouter **directly, with no proxy** (unlike
codex's Responses API, which needs one). Export your key once and pick the backend:

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
workhorse --workflow ./wf/workflow.yaml --cli opencode   # or: --cli aider
```

Point the power tier at the model in your config, so the same workflow still runs
natively under `--cli claude`:

```toml
[power.high.opencode]
model = "openrouter/xiaomi/mimo-v2.5"
```

| Trait | `aider` | `opencode` |
|---|---|---|
| Invocation | `aider --message` (single-message coder) | `opencode run --format json` (agentic loop) |
| Output | plain-text transcript (captured whole) | NDJSON events |
| Session resume | none — ladder reframes | by id (`--session`) |
| Reasoning effort | `--reasoning-effort` (clamped to `high`) | `--variant` (minimal/high/max) |
| Editing | search/replace diffs (robust on weak models) | tool-calling |

**Provider pin + prompt caching (MiMo).** MiMo-V2.5 has two OpenRouter providers;
only `xiaomi` serves the implicit prompt cache (~98% off input on every turn). Pin it
in the **harness's own config** — there is no workhorse proxy to do it for you:

- **opencode** caches automatically (verified: `cache.read` fires); pin the provider
  in `opencode.json` provider options (`provider.openrouter` → routing → `order:
  [xiaomi]`, fallbacks off).
- **aider** is litellm-based: set
  `extra_params.extra_body.provider.order: [xiaomi]` (plus `--cache-prompts`) in a
  `--model-settings-file`.

## Resuming and run identity

The controller is **auto-resume-in-place** by default. Each `(workflow, run-id)`
pair maps to one stable run dir (`<workflow>-<run-id>`, run-id defaults to
`default`). On start the controller looks for a checkpoint there:

- **No checkpoint** → start fresh from the `start` node in that dir.
- **Checkpoint present** → resume from the checkpointed node, restoring the saved
  context. A node that finished but didn't advance the cursor (killed in the gap)
  is fast-forwarded past rather than re-run, so side effects like git commits
  aren't duplicated.

This is what lets an unattended run survive a crash or reboot: relaunching the
same workflow continues where it left off. To start over, delete the run dir. To
keep independent runs of the same workflow side by side, pass distinct run ids.

Controller flags (passed to `workhorse`; `--resume-*` are manual overrides
of the auto behavior above):

| Flag | Purpose |
|---|---|
| `--run-id <id>` | Name the stable run dir (`<workflow>-<id>`); default `default` |
| `--resume-run <path-or-name>` | Resume a specific run dir from its checkpoint |
| `--resume-latest` | Resume the most recent unfinished run under `--runs-dir` |
| `--params '<json>'` / `--params-file <path>` | Override workflow `vars` on a fresh start |

"Survives reboot" therefore covers both the *work products* (commits, sessions,
artifacts) **and** graph position — an interrupted graph auto-resumes mid-run.

## Run artifacts

Each workflow execution writes a timestamped directory:

```
runs/
└── <workflow-name>-<timestamp>-<id>/
    ├── run.json                  # start/end time, terminal state
    ├── context.json              # final context snapshot
    ├── <step-id>/
    │   ├── prompt.md             # rendered prompt, written before agent invocation
    │   ├── output.json           # extracted JSON outputs
    │   └── context_after.json    # context state after this step
    └── <branch-id>/
        └── branch.json           # { path, value, next }
```

Artifacts are written under `--runs-dir` (default `<workflow-dir>/runs`). Before
each agent turn, workhorse writes the rendered `prompt.md` and logs only that path
so failed or interrupted nodes remain inspectable without dumping variables. The
Docker harness redirects artifacts to a persistent volume instead — see
[docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).

## Telemetry (opt-in OpenTelemetry)

For away-from-keyboard monitoring of long runs, workhorse can stream OpenTelemetry
spans and metrics to a local OTLP collector — by default `groom`, which stores them
in SQLite and pages you (ntfy/webhook + browser) on stall/budget/churn:

```bash
pip install 'workhorse-agent[otel]'
export WORKHORSE_OTEL=1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787   # groom serve (the default)
```

Emitted: a root span per run, a span per node visit (nested through flows), a span
per agent-CLI turn with duration + token usage, span events for the recovery ladder
(retry/reframe/compact/watchdog-kill), the gas gauge, and a **cap-wait heartbeat**
metric each pause tick — the signal that lets a collector distinguish a legitimate
multi-day spending-cap sleep (heartbeating = alive) from a hang (silence). Unset,
telemetry is a complete no-op and adds no dependencies; exports are best-effort, so
a down collector can never slow or wedge a run. Any standard OTLP/HTTP backend
(Jaeger, Grafana Tempo) works unchanged. There is also an engine wall-clock ceiling,
`WORKHORSE_MAX_RUNTIME_S` — see
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md)
for both.

## Repository isolation

`workhorse` is repository-agnostic — it never assumes a particular repo or working
tree. If a workflow needs to operate on source code (read, edit, build, test),
include a `setup.sh` script in the workflow directory. It runs as the first node
and clones the required repositories to a known path. This keeps the workflow
reproducible and lets the agent work from a clean, versioned checkout rather than
a host working tree. See any workflow's `scripts/setup.sh` for an example. (The
Docker harness builds on this to give each run a fully isolated, throwaway clone —
see [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).)

## Writing a workflow

> **Full schema reference:** [docs/WORKFLOW.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/WORKFLOW.md) documents every
> top-level key, every node type and field, the `OutputSpec`/branch syntax, and
> the templating context. The overview below is the quick version.

A workflow is a directory with this layout:

```
my-workflow/
├── workflow.yaml       # Graph definition
├── prompts/            # Jinja2 .md templates
│   └── step.md
└── scripts/            # Shell or Python scripts (must output JSON to stdout)
    └── check.sh
```

**`workflow.yaml` schema:**

```yaml
name: my-workflow
vars:
  my_var: "default value"   # Initial context variables

start: first_node

nodes:
  - id: first_node
    type: agent              # agent | script | branch | terminal | fail
    prompt: prompts/step.md
    args:
      key: "{{ my_var }}"   # Jinja2 — rendered against context before sending
    outputs:
      - key: result          # Extract this key from the agent's JSON response
        default: {status: ok} # Optional: emitted if the node exhausts all retries
                              # (see "Unattended resilience" below). Unset → null.
    next: check_result

  - id: check_result
    type: branch
    path: result.status      # Dot-path into context
    cases:
      ok: done
      error: done
    default: done

  - id: done
    type: terminal
```

**Branch operators** — in addition to `cases` (equality map), you can use `conditions` for numeric comparisons:

```yaml
  - id: decide
    type: branch
    path: result.count
    conditions:
      - op: ">="
        value: "10"
        next: bulk_path
    default: single_path
```

Supported operators: `==`, `!=`, `<`, `>`, `<=`, `>=`.

**Agent prompts** must output JSON containing the declared output keys:

```markdown
Do the thing.

Output JSON only:

```json
{"result": {"status": "ok", "count": 5}}
```
```

**Scripts** receive Jinja2-rendered args as positional arguments and must print JSON to stdout:

```bash
#!/bin/bash
echo "{\"result\": {\"status\": \"ok\"}}"
```

### Unattended resilience (output `default`)

Because runs are meant to survive a week without supervision, the controller
will, as a last resort, **default an agent node's outputs and advance to `next`**
rather than crash when Claude can't be coaxed into a usable answer (after
transient retries and prompt reframing — see [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md)).

The runner is generic and doesn't know what your outputs mean, so **you** declare
the safe fallback per output via `default`:

```yaml
    outputs:
      - key: decision
        default: continue          # branch-safe value if this node never answers
      - key: review
        default: {status: auto_approved}
      - key: notes                 # no default → emitted as null
```

Choose defaults that keep the graph moving sensibly (e.g. a branch `path` that
lands on a safe route). An output with no `default` is emitted as `null`. To
disable defaulting entirely and hard-fail instead, set
`AGENT_USE_DEFAULT_OUTPUTS=false`.

## Development

This section is for working on the **controller itself** (the Python that runs
workflows), not on individual workflows. It assumes you have cloned the source
repository (the `agents/local-worker/` directory) rather than installed from PyPI.
Common tasks are wrapped in the [`Makefile`](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/Makefile) (`make help`):
`make install`, `make test`, `make build`, `make publish`.

### Project layout

```
agents/local-worker/          # source repo dir for the workhorse controller
├── workhorse/                 # The workhorse Python package (entrypoint: workhorse:main)
│   ├── main.py                # CLI + the graph walk loop: checkpoint → run node → advance
│   ├── templates.py           # Jinja2 rendering (resilient: missing vars render empty, not raise)
│   ├── artifacts.py           # ArtifactWriter: run dir, checkpoints, per-step artifacts
│   ├── otel.py                # Opt-in OpenTelemetry facade (no-op unless WORKHORSE_OTEL is set)
│   ├── graph/
│   │   ├── nodes.py           # Pydantic node models (AgentNode/ScriptNode/BranchNode/TerminalNode) + Graph
│   │   ├── loader.py          # Parse + validate workflow.yaml into a Graph
│   │   ├── context.py         # WorkflowContext: the key→value bag + dot-path lookup for branches
│   │   └── dot.py             # Render a Graph to Graphviz DOT (the `workhorse dot` subcommand)
│   └── runner/
│       ├── agent.py           # Invoke Claude CLI; the retry → reframe → default resilience ladder
│       ├── script.py          # Run a ScriptNode, capture JSON stdout
│       └── branch.py          # Evaluate a BranchNode (cases / numeric conditions / default)
├── tests/                     # Standalone test files (see below)
├── compose.yaml               # Service, env, mounts, named volumes
├── Dockerfile                 # Ubuntu + uv + Claude CLI + the controller package
├── entrypoint.sh              # Non-root auth seeding, checkout, exec `workhorse`
├── Makefile                   # install / test / build / publish tasks (`make help`)
├── pyproject.toml / uv.lock   # Python deps (jinja2, pyyaml, pydantic); managed with uv
├── README.md                  # This file (usage + development)
├── CLAUDE.md                  # Agent entry point; imports README.md + docs/
└── docs/
    ├── GUARDRAILS.md          # The resilience/error-recovery design and env-var reference
    └── DOCKER.md              # The Docker harness (image + compose) for unattended runs
```

### How the controller works (the loop)

`main.run()` is a single loop over graph nodes. For each node it:

1. **Checkpoints** the current node id + context (`ArtifactWriter.write_checkpoint`) so a crash here is resumable.
2. **Dispatches** by node type to a runner: `runner/agent.py`, `runner/script.py`, or `runner/branch.py`.
3. **Merges** the node's outputs into the `WorkflowContext`.
4. **Writes** a per-step artifact and advances `current_id` to `node.next` (or the branch target).

A `terminal`/`fail` node ends the loop. The resilience for `agent` nodes lives
entirely in `runner/agent.py::run_agent` — see [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

### Sessions (per-node clean context)

**Each node runs as a fresh prompt with a clean Claude context.** The controller
does *not* chain one node's conversation into the next — node N does not inherit
node N‑1's messages. Concretely, `run_agent` drops any persisted `.session_id`
before a node's first attempt, and a reframed attempt also starts fresh.

The persisted session is `--resume`d in exactly one situation: **continuing the
same node that was interrupted.** When the controller resumes from a checkpoint
and re-enters a node that was killed mid-run (not fast-forwarded), it calls
`run_agent(..., resume_session=True)` for that one node so Claude picks up where
it left off; every node the run then advances to starts clean again.

**Context overflow → compact & continue.** If a node exhausts the model's
context window mid-run (the headless CLI returns instead of auto-compacting),
`run_agent` runs `/compact` on that node's session and retries the *same* prompt
on it, preserving the node's progress (bounded by `AGENT_MAX_COMPACT_ATTEMPTS`;
falls back to a fresh-session reframe if `/compact` can't help). Verified against
Claude Code 2.1.x. See the recovery ladder in [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

> Not yet implemented: a configurable *per-node turn limit* (`--max-turns`) that
> proactively compacts before the window is exhausted. Today compaction is
> reactive — triggered when an overflow is detected.

### Running tests

Tests live in `tests/` and are **dependency-free**: each file runs standalone
(`python tests/test_x.py` prints PASS/FAIL and exits non-zero on failure) and is
also pytest-compatible. There is no pytest in the venv by default; run them with
the project's Python:

```bash
# All of them (via the Makefile)
make test

# One file
uv run python tests/test_agent_recovery.py
```

If a `.venv` isn't present, create one with `uv sync` (or `make install`).

**Where to put tests.** Add a `tests/test_<area>.py`, mirroring the existing
style: a `if __name__ == "__main__"` runner that iterates `test_*` functions, and
unit tests that patch the CLI boundary (`_run_claude_cli` / `_invoke_claude`) and
sleeping so nothing hits the network or waits in real time. Group by concern:
`test_agent_cap.py` (cap/transient handling), `test_agent_recovery.py` (reframe →
default ladder), `test_branch_guardrail.py`, `test_resume_auto.py`,
`test_idempotency.py`, `test_templates_resilient.py`.

### Where docs go

- **Tool/usage + development docs** → this `README.md` (root).
- **Design notes** (resilience/error recovery) and the **Docker harness** →
  `docs/`, e.g. `docs/GUARDRAILS.md`, `docs/DOCKER.md`. Put new long-form design
  and deployment docs here rather than at the root.
- **`CLAUDE.md`** (root) is the agent entry point and stays at the root so Claude
  Code auto-loads it; it `@`-imports `README.md` and `docs/GUARDRAILS.md`.
- **Per-workflow docs** → inside that workflow's own directory (under
  `../workflows/<name>/`), not here. The controller is workflow-agnostic; keep
  workflow-specific knowledge with the workflow.

Keep these docs current when you change behavior — they are the contract for
operators running week-long jobs, and `CLAUDE.md` imports them, so updating them
keeps agent context accurate too.

### Conventions

- **Python 3.12**, `from __future__ import annotations` at the top of each module.
- **Pydantic** models for anything parsed from YAML (see `graph/nodes.py`); add a
  new node type by extending the discriminated `Node` union and handling it in
  `main.run()` plus a `runner/`.
- **Fail soft for unattended runs.** New failure paths in agent handling should
  slot into the existing retry → reframe → default ladder rather than raising, so
  one bad node can't end a week-long run. Reserve hard raises for genuinely
  unrecoverable, deterministic errors.
- **Comments explain *why*.** Match the existing density — the tricky invariants
  (checkpoint/fast-forward idempotency, cap-vs-transient classification) are
  documented inline; keep them that way.

### Editing the container

The repo ships a Docker harness (`Dockerfile`, `compose.yaml`, `entrypoint.sh`)
for isolated unattended runs. It is not part of the PyPI package; its build/run
workflow — including rebuilding the image after controller or `pyproject.toml`
changes — is documented in [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).
