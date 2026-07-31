# workhorse

[![PyPI](https://img.shields.io/pypi/v/workhorse-agent.svg)](https://pypi.org/project/workhorse-agent/)

**A fail-soft runner for YAML-defined agent workflows — drives an agent CLI
(Claude, Codex, or Copilot) through a workflow graph unattended for days.**

A workflow is a graph of `agent`, `script`, and `branch` nodes. `workhorse` walks
the graph, renders Jinja2 prompts, invokes the agent CLI or Python scripts,
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
| `--run-id <id>` | Name the stable run dir (`<workflow>-<id>`); default: a digest of `--params`, else `default` |
| `--cli {claude,codex,copilot,aider,opencode}` | Which agent CLI drives the run (default `claude`; or `AGENT_CLI`) |
| `--params '<json>'` / `--params-file <path>` | Override workflow `vars` on a fresh start |
| `--dry-run` | Check the workflow and exit without running a node (see [Checking a workflow before you run it](#checking-a-workflow-before-you-run-it)) |
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
workhorse config set-library ~/path/to/overlay-library      # optional private overlay
workhorse config set-stablemate ~/path/to/stablemate        # optional: sets CODER_WORKSPACE
```

`--workflow` and the `run` positional form are equivalent — use whichever fits the
context. The overlay library path can also be set via `WORKHORSE_LIBRARY_DIR`.

A name resolves through two mechanisms, in order: an **installed workflow package**,
then the **library layers**.

A distribution ships workflows by advertising them in the `workhorse.workflows`
entry-point group, and `workhorse run <name>` resolves the package that claims the name:

```toml
[project.entry-points."workhorse.workflows"]
research = "myworkflows.research.workflow:workflow"
```

An installed package wins over a library layer of the same name — installing one is a
deliberate act aimed at that name, while a library layer is the content store a name
falls back to. When both exist, workhorse says so on stderr and the library copy stays
reachable by path. The package must be installed **unpacked** (any pip/uv wheel is): the
prompt renderer is a filesystem template loader rooted at the workflow's own directory,
so a zip-imported package is refused at resolution rather than failing later as a
missing template.

Failing that, a named workflow resolves across two layers: the configured overlay
(above) and the **base library** beneath it. You do not install the base — it is content, and workhorse
fetches it into `~/.cache/stablemate` the first time it needs one, then leaves it frozen
(delete the cache to upgrade). It finds a base via, in order: `$STABLEMATE_BASE_DIR` →
the `base_dir` config key (`workhorse config set-base <path>`) → an import of the
`stablemate-library` wheel from workhorse's own environment → a `stablemate_dir`
checkout → the shared cache. The fetched copy is last, so it never shadows a base you
chose. See the monorepo README's
[Installing](https://github.com/GabrielCpp/stablemate#installing) section.

A workflow declares the tools it uses in a `requires:` block, checked before the first
node runs — see [docs/WORKFLOW.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/WORKFLOW.md#11-requires--declaring-the-tools-a-workflow-uses).
Script nodes run under workhorse's own interpreter, so a tool they import must live in
*that* environment (`pipx inject workhorse-agent ostler`), not merely on `PATH`.

The skill and prompt references its prompts make are checked in the same breath. A
`{{ instruction_ref("story-docs") }}` that resolves against nothing does not fail — it
renders the sentence `generated story-docs instruction file when installed` into a live
agent prompt, and the agent is left to find the skill itself. Before the first node,
workhorse parses the workflow's `prompts/**/*.md`, resolves every constant reference
against the loaded context manifest, and prints the ones that will not resolve, with the
fix (add them to the repo's `agents.yml` selection and re-run `make agent-install`). It is
a warning, not an error: the run is degraded, not impossible. A run carrying **no**
manifest at all (`hello-world`, most tests) is skipped — there, unresolved is the normal
state. References built from a computed argument can't be seen statically; those log a
`[template] ⚠` line when they render instead.

### Per-workflow commands (`workhorse-<name>`)

A distribution may also install one console script per workflow, alongside the entry
point:

```toml
[project.scripts]
workhorse-research = "myworkflows.research.workflow:main"
```

```bash
workhorse run research qa --run-id=r1 --params '{"k":"v"}'
workhorse-research  run qa --run-id=r1 --params '{"k":"v"}'   # identical
```

The two are the same command: one parser, with the workflow name already bound in the
second. `workhorse-<name>` therefore accepts exactly what `workhorse run` accepts and
nothing more — for `dot`, `test` or `config`, use `workhorse`.

> **Running unattended in a container?** The source repo ships a Docker harness
> (image + compose) for fully isolated, week-long runs with credential seeding
> and persistent volumes. It is *not* part of the PyPI package — see
> [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).

## Checking a workflow before you run it (`--dry-run`)

`--dry-run` checks a workflow and exits without running a node — `0` when it is
clean, `1` on the first problem, so CI can read it. The failure it exists to catch
is a typo found at hour 30 of an unattended run.

```bash
workhorse run coder --dry-run
```

For a YAML workflow it loads the graph and turns the skill/prompt reference warning
described above into an exit code, then prints the node list.

For a workflow written as a Python state machine it does the same reference check —
the prompts are read from the workflow's own directory either way — and then two
complementary things.
First a **static pass** over the states' own source (the same reading `dot` uses):
every prompt path a state renders must exist, every state must be reachable from the
start state, at least one state must be able to return `Done`, and no transition may
name something that is not a state. Then it **drives the machine for real** over a
*substituted node index*, which covers what only running can — imports, `setup()`, and
the transitions actually bound along one path. The static half is the one that carries
the weight: it sees the branches this run would never take.

Nothing branches on "is this a dry run" inside the engine. The run is handed a copy of
the registry's node index with every node's body replaced by its stand-in, so `self.call`
runs the same code path it always does — see
[The node index is the substitution seam](#the-node-index-is-the-substitution-seam).
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

## Diagramming a workflow (`workhorse dot`)

`workhorse dot` renders a workflow graph to [Graphviz](https://graphviz.org) DOT
straight from the workflow, so the diagram never drifts from it. For a YAML
workflow, styling is type-based: branch nodes are salmon diamonds, terminals green,
`fail` nodes coral, agent/script nodes plain boxes; branch edges are labeled with
their case / numeric-condition / `default`.

```bash
workhorse dot ./wf/workflow.yaml            # DOT to stdout
workhorse dot coder -o wf.dot               # ...by name, to a file
dot -Tsvg wf.dot -o wf.svg                  # render (needs graphviz)
```

A name that resolves to a **Python state machine** is rendered from its states
instead: one cluster per flow, a `box3d` green node for every state that can return
`Done`, dashed orange edges for an `Await`, coral for a state nothing reaches, and
edge labels naming the parameters each transition binds. The graph is read off the
states' source, so both arms of an `if` appear (it over-approximates) and it cannot
drift from the code. A state that factors a repeated turn into a private helper keeps
its annotations: `self._helper(...)` is followed into the class's own underscore
methods, and what it finds is attributed to the state that called it — the helper is
not a node. Aliases are never drawn as a second state. `--pin`/`--leaf` are
declined there rather than ignored — they collapse a *declared* branch, and a Python
workflow's branches are code.

| Flag | Purpose |
|---|---|
| `--workflow <path-or-name>` | The workflow to render; equivalent to the positional form |
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

#### Per-harness environment (`[harness.<backend>].env`)

Some harness knobs exist only as **environment variables** — no CLI flag, no
setting workhorse could pass through. Name them per backend and workhorse exports
them into that CLI's subprocess (and nothing else's):

```toml
[harness.opencode]
env = { OPENCODE_DISABLE_AUTOCOMPACT = "1" }

[harness.claude]
env = { MAX_THINKING_TOKENS = "31999" }
```

Applied on top of the inherited environment, so a variable set here wins over the
same one exported by the launching shell. Values must be **strings**: `env = { FOO
= 1 }` is a TOML integer and is dropped rather than coerced, so the config can't
claim to have set something the process never received.

Workhorse learns no harness's vocabulary here — it forwards whatever you name. It
also does not validate the names, so a typo is silent; check the harness's own docs
for what it reads.

The worked example is the one above. `opencode` auto-summarizes a long session, and
each summary rewrites the conversation prefix — so the next turn bills a full-price
prompt instead of a cache read. On a model whose context window you will never
approach (the 1M-token OpenRouter endpoints in [OpenRouter models](#openrouter-models--aider-and-opencode)),
that is pure cost with nothing gained. Turning it off is right for *those* runs and
wrong for a run against a 272k window, which is exactly why it is scoped to the
harness config rather than set globally in `~/.config/opencode/opencode.jsonc`.

Scoped per **harness**, not per power tier: a knob like that is a property of the
CLI, not of how hard a node is thinking. (And unlike `model`/`effort`, which resolve
by "first layer that names one wins", an env table would want to *merge* across
layers — so a second layer would be a different resolution rule, not more of the
same one.)

Inspect or set config:

```bash
workhorse config show                        # print all config keys
workhorse config show power.high.claude      # print one value
workhorse config set-library ~/path/to/lib   # set the overlay library path
workhorse config set-stablemate ~/path/to/sm # set the stablemate checkout path
workhorse config set-base ~/path/to/base     # set the base library content path
workhorse config list                        # list all config keys (power table friendly)
workhorse config get power.high.claude       # get one key
```

#### Config file location

Config lives in **one file shared with farrier**, at a platform-appropriate path (via
[platformdirs](https://github.com/tox-dev/platformdirs)):

| Platform | Default path |
|---|---|
| macOS | `~/Library/Application Support/stablemate/config.toml` |
| Windows | `%APPDATA%\stablemate\config.toml` |
| Linux | `~/.config/stablemate/config.toml` |

Override the path with `STABLEMATE_CONFIG=/path/to/config.toml` (the older
`WORKHORSE_CONFIG` is still honored).

It is one file because `library_dir`, `stablemate_dir` and `base_dir` only mean anything
if every tool agrees on them — with a file per tool, `workhorse config set-base` and
`farrier config set-base` wrote to different places and could silently disagree. The
pre-unification per-tool files (`~/.config/workhorse`, `~/.config/farrier`) are still
read when the shared one is absent, and the first write folds them into it, so an
existing setup keeps working with no migration step.

#### Config schema version

The file carries a `config_version`. workhorse and farrier are installed separately and
versioned independently, so the file — not the code — is where they are kept in step:

| Situation | Behavior |
|---|---|
| Config is newer than this build | `config set-*` **refuses** (exit 1). Upgrade workhorse. |
| Config is older than this build | Migrated forward on the next write; the old file is kept as `config.toml.v<n>.bak`. |
| Reading a newer config | Succeeds, logs a warning. |

Reads deliberately never raise: `power` is re-read per node, so a hard failure would kill
an unattended run mid-flight because some other tool was upgraded. Writes are the guard,
because a writer that does not understand a key drops it — which is exactly the bug that
made this one file in the first place.

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

**Pin the upstream endpoint — it is the largest cost lever, not a tuning detail.**
An OpenRouter *model* is a fan-out over many upstream *endpoints*, and they differ on
the two things a long run is made of:

- **Price.** Across GLM 5.2's 33 endpoints the input price spans **7.0x**; across
  MiMo-V2.5-Pro's 6 it spans 5.3x. Cache-read discounts diverge further — 98–99% off
  on the best endpoints, ~64% on others.
- **Context window.** Same model slug, windows from 96k to 1.05M. An unpinned run can
  fail over onto a 96k endpoint mid-workflow and start overflowing on prompts the
  previous turn handled fine.

And a prompt cache lives **on the endpoint**, so every silent failover starts a cold
prefix: the next turn bills a ~100k-token prompt at full input price. Left to default
routing, none of this is visible — the run just costs more.

Pin it in the **harness's own config** (there is no workhorse proxy to do it for you),
choosing endpoints by *tag slug* (`baidu/fp8`, not `baidu`), with fallbacks off so
drift surfaces as an error rather than a bill:

- **opencode** caches automatically (verified: `cache.read` fires). In
  `~/.config/opencode/opencode.jsonc` set
  `provider.openrouter.models.<slug>.options.provider` to
  `{ "order": [...], "allow_fallbacks": false }`, and
  `provider.openrouter.options.setCacheKey: true` to send `prompt_cache_key` so repeat
  turns route back to the node holding the prefix.
- **aider** is litellm-based: set the same object at
  `extra_params.extra_body.provider` (plus `--cache-prompts`) in a
  `--model-settings-file`.

List the current endpoints, prices and windows before choosing — they change:

```bash
curl -s https://openrouter.ai/api/v1/models/xiaomi/mimo-v2.5-pro/endpoints \
  | jq -r '.data.endpoints[] | [.tag, .context_length, .pricing.prompt,
                               .pricing.input_cache_read, .uptime_last_30m] | @tsv'
```

**Turn opencode's auto-summarization off for runs on a huge-window endpoint** — but
per run, not globally. Each auto-compaction rewrites the conversation prefix and so
throws the cache away; when the pinned endpoint carries a 1M window and the workflow
never exceeds ~200k, that summary buys nothing and costs a cold prompt:

```toml
# ~/.config/stablemate/config.toml
[harness.opencode]
env = { OPENCODE_DISABLE_AUTOCOMPACT = "1" }
```

…or for a single run, `OPENCODE_DISABLE_AUTOCOMPACT=1 workhorse run <workflow> --cli
opencode`. Either way it is scoped to the harness, which is the point: do **not** set
`"compaction": {"auto": false}` in `opencode.jsonc`, because that key is global with
no per-provider scope and would also disable compaction for models that run close to
their ceiling and rely on it. See
[Per-harness environment](#per-harness-environment-harnessbackendenv). Note the ladder still covers a
genuine overflow either way — opencode exposes no in-place `/compact`
(`supports_compaction = False`), so workhorse reframes the node in a fresh session
rather than compacting.

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

- **No checkpoint** → start fresh from the `start` node in that dir.
- **Checkpoint present** → resume from the checkpointed node, restoring the saved
  context. A node that finished but didn't advance the cursor (killed in the gap)
  is fast-forwarded past rather than re-run, so side effects like git commits
  aren't duplicated.

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
| `--params '<json>'` / `--params-file <path>` | Override workflow `vars` on a fresh start (also keys the default run dir) |

"Survives reboot" therefore covers both the *work products* (commits, sessions,
artifacts) **and** graph position — an interrupted graph auto-resumes mid-run.

## Run artifacts

Each workflow execution writes a timestamped directory:

```
runs/
└── <workflow-name>-<timestamp>-<id>/
    ├── run.json                  # start/end time, terminal state, interrupt stamp
    ├── context.json              # final context snapshot
    ├── sessions.jsonl            # {node, session_id} per agent turn — map a node to its CLI session
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

`prompt.md` and `output.json` capture a node's *input* and *final* answer, not the
agent's step-by-step reasoning and tool calls in between — that transcript lives in
the agent CLI's own session store, keyed by session id. `sessions.jsonl` records the
`node → session_id` map for every agent turn so you can recover it afterward (e.g.
`opencode export <session_id>`). It is an append-only manifest because the live
`.session_id` file holds only the *current* node's session; a node can appear more
than once (loop revisits, compact/reframe within a node), so the mapping is
`node → sessions` and consumers dedup on read. With telemetry on the same
session id is also set as the `session.id` attribute on the agent-turn span.

## Telemetry (automatic when a collector is reachable)

For away-from-keyboard monitoring of long runs, workhorse streams OpenTelemetry
spans and metrics to a local OTLP collector — by default `groom`, which stores them
in SQLite and pages you (ntfy/webhook + browser) on stall/budget/churn. Install the
extra once and it turns itself on whenever the collector is up:

```bash
pip install 'workhorse-agent[otel]'
groom serve                                                # now every run is observed
```

**Enablement is a tri-state.** With `WORKHORSE_OTEL` unset (the default),
`start_run` opens one short TCP connection to the endpoint and enables telemetry
only if something is listening — so a machine running `groom serve` gets spans with
no env var, and a machine without one stays a complete no-op. Set it explicitly to
override that decision in either direction:

| `WORKHORSE_OTEL` | Behavior |
|---|---|
| _unset_ (default) | **Auto** — probe the endpoint; enable only if it answers |
| `1` / `true` / `yes` | Force on — no probe (for a collector that comes up later, or one a TCP connect can't see) |
| `0` / `false` / `no` | Force off — no probe, never enabled |

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787   # groom serve (the default)
export WORKHORSE_OTEL=0                                    # opt out of auto-on
```

Auto-on is the default because the runs most worth observing are the unattended
week-long ones — exactly the runs nobody remembers to export a variable before
launching. Without the `otel` extra installed, auto mode stays silently inert (an
explicit `WORKHORSE_OTEL=1` still warns that the SDK is missing, since you asked).

Emitted: a root span per run, a span per node visit (nested through flows), a span
per agent-CLI turn with duration + token usage + cost (and a `session.id` attribute
linking it to the CLI session transcript), span events for the recovery ladder
(retry/reframe/compact/watchdog-kill), the gas gauge, **log records** from the
engine and its in-process script nodes (`groom logs`), and a **cap-wait heartbeat**
metric each pause tick — the signal that lets a collector distinguish a legitimate
multi-day spending-cap sleep (heartbeating = alive) from a hang (silence). With no
collector reachable, telemetry is a complete no-op and adds no dependencies;
exports are best-effort, so a collector that dies *mid-run* can never slow or wedge
a run either. Any standard OTLP/HTTP backend
(Jaeger, Grafana Tempo) works unchanged.

**Turn spans are comparable across backends.** Every harness reports what a turn
consumed and every one spells it differently, so workhorse normalizes them onto one
set of attribute names (Claude's, since those spans are already in the store): tokens
in/out, cache read/write, reasoning tokens, and `total_cost_usd` where the harness
reports money at all. Cost is left *absent* rather than zeroed when a harness doesn't
say — a real `0.0` (a subscription turn) and "this CLI doesn't report cost" are
different facts, and averaging them together understates spend. `duration_ms` is
stamped by the engine when the CLI omits it, so latency coverage is total regardless
of harness. Backends that report per *step* rather than per turn (opencode) are summed.

**Tag spans with your own unit of work** via a workflow's `labels:` block — Jinja
templates re-rendered before every node and stamped as `wf.*` span attributes. Without
it a store can group by run and node but not by task; see
[docs/WORKFLOW.md §1.2](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/WORKFLOW.md#12-labels--tagging-telemetry-with-the-unit-of-work).

There is also an engine wall-clock ceiling,
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
└── scripts/            # Python scripts (must output JSON to stdout)
    └── check.py
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

**Scripts** are Python. Workhorse **imports the script and calls its
`main(logger)`** in its own process; they receive Jinja2-rendered args as
positional `sys.argv` entries and must print JSON to stdout:

```python
import json
import logging

def main(logger: logging.Logger) -> None:
    logger.info("deciding...")                      # diagnostics → the logger
    print(json.dumps({"result": {"status": "ok"}})) # data → stdout
```

stdout is the node's **data** channel — it is parsed whole as the declared
`outputs`, so diagnostics must go to the logger, never `print`. With
telemetry on, those records reach the collector tagged with the run and node.
`def main()` (no logger) and scripts with no `main()` at all keep working
unchanged. See [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md)
for the isolation trade-off and `WORKHORSE_SCRIPT_INPROCESS=0`.

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

## Writing a workflow in Python (`workhorse.pyflow`)

A workflow may also be written as a **Python state machine** instead of a YAML graph.
The two engines share the runs directory, the artifact layout, the agent backends, the
telemetry and the resilience ladder; what differs is where control flow lives. YAML puts
it in `branch` nodes and context keys; `pyflow` puts it in ordinary Python — `if`,
`for`, a counter that is just a counter.

```python
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
main = workflow.main(Build)                        # the console script; see above
```

### The three tiers of state, and no fourth

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

### Where an agent turn runs (`cwd` / `add_dirs`)

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
turn sees. It is the same field the YAML `agent` node carries, and the runner de-dupes
`add_dirs` against it and turns the rest into `--add-dir` flags, so the behavior is
identical across both engines.

The difference is that these are **real values, not Jinja templates**. A YAML node writes
`cwd: "{{ cfg.repo_root }}"` because YAML has no other way to compute one; a state
computes the path in Python and passes it.

### Transitions

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

### Checkpoints and renaming

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

The two engines recognize each other's checkpoints and refuse them by name, in both
directions: they share one runs directory and one `--resume-latest`, and a state name
that happens to match a node id would otherwise resume the wrong thing.

### The node index is the substitution seam

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
pyflow_engine.agent_runner.run_agent = agent
with patch("workhorse_workflows.research.nodes.setup.allow_all_directories"):
    ...
```

```python
# after — the same two dependencies, handed to the run
RunEnv(
    ...,
    run_agent=agent,
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

### Labels, and saying what the run is doing

A workflow declares its telemetry dimensions by overriding `labels()`, the counterpart of
the YAML `labels:` block. It takes no arguments and is re-read before every transition, so
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

Unlike the YAML engine these keys are **not** `wf.`-prefixed. The prefix existed so a
workflow could not shadow an OTel convention; here the collector reads the unprefixed
spelling, and nothing is translated on the way out. Both spellings of `activity` and
`work_id` are promoted onto the live gauges, so each engine's own keys reach a dashboard
untouched.

**Activity — what the run is working on right now — is a flagged log record**, not a
field:

```python
    def assess(self, unit_id: str):
        self.logger.info("assessing %s", unit_id, extra={"activity": True})
```

The rendered message *is* the activity: `activity` is a flag, not a value, so the text is
never written twice and never drifts from what the log says. A YAML node hangs this on a
per-node `activity:` string, but a state is one method that may do several things and the
interesting one is whichever it is doing now — and a `@blueprint.node` is a plain function
with no `self`, so its injected `logger` is the only route it could have. Both are the same
logger object, so both work identically.

It is **sticky**: the last flagged line stands until another replaces it, so a state that
flags once and then works for an hour stays correctly labelled. Nothing flagged yet falls
back to the node id, which the gauges stamp anyway.

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
│   ├── otel.py                # OpenTelemetry facade (auto-on if a collector answers; else no-op)
│   ├── graph/
│   │   ├── nodes.py           # Pydantic node models (AgentNode/ScriptNode/BranchNode/TerminalNode) + Graph
│   │   ├── loader.py          # Parse + validate workflow.yaml into a Graph
│   │   ├── context.py         # WorkflowContext: the key→value bag + dot-path lookup for branches
│   │   └── dot.py             # Render a Graph to Graphviz DOT (the `workhorse dot` subcommand)
│   ├── pyflow/                # The Python state-machine engine (the YAML engine's sibling)
│   │   ├── workflow.py        # The `Workflow` base class: state discovery, freezing, self.ctx
│   │   ├── transitions.py     # Continue / Done / Await + transition-time signature binding
│   │   ├── blueprint.py       # `Blueprint`: node libraries a workflow composes
│   │   ├── registry.py        # What an entry point / console script points at
│   │   ├── engine.py          # self.call / self.agent / self.handoff / self.output
│   │   ├── driver.py          # drive(): the state loop, the (state, params) checkpoint, Await
│   │   ├── activity.py        # The flagged-log-record activity tracker (a logging.Filter)
│   │   └── names.py           # NameIndex: live names + aliases, collisions raise at import
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

**Where to put tests.** There are two styles. Controller-internal tests add a
`tests/test_<area>.py` that patches the CLI boundary (`_run_claude_cli` /
`_invoke_claude`) and sleeping so nothing hits the network or waits in real time:
`test_agent_cap.py` (cap/transient handling), `test_agent_recovery.py` (reframe →
default ladder), `test_branch_guardrail.py`, `test_resume_auto.py`,
`test_idempotency.py`, `test_templates_resilient.py`.

**Whole-workflow tests** use the in-process harness in `workhorse.testing`
(`WorkflowRun`). It runs the engine **in the current process** — no `workhorse`
CLI subprocess and no PATH shims. Agent nodes are answered by `mock_agent` /
`mock_agent_sequence`; Python script nodes run in-process via `runpy`, so a test
`monkeypatch`es the `workhorse.scriptutil` seams a script calls — `github_client`
(the PyGithub client, so GitHub is faked with no `gh` CLI) and `run_tool`
(external CLIs like `ostler`). Local `git` runs for **real** against a throwaway
repo built with `make_git_repo` — git is never mocked. Assert on the `RunResult`
(`passed()`, `step_outputs(node)`, `prompt(node)`, `context()`, `calls(cli)`,
`has_warning(text)`).

For those patches to survive, the harness sets `WORKHORSE_FRESH_IMPORT=0` for the
duration of a run. A script that calls `scriptutil.fresh_import` normally re-imports
from disk and so gets a **new module object**, silently discarding every seam the test
patched onto the old one — the mock is still in place, just no longer the thing the
script calls. Nothing edits a package on disk mid-run under the harness, which is the
only situation `fresh_import` exists for, so switching it off there costs nothing.

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
