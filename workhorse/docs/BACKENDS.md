# Agent CLI backends, models and config

workhorse drives **one agent CLI per run** and picks **one model per agent turn**. This
document covers both halves: choosing the backend (`claude`, `codex`, `copilot`, `cline`,
`opencode`), and how a turn's abstract `power` tier resolves — through the config file
workhorse shares with `farrier` — into a concrete model and effort. It also covers the two
backends that need more than a flag: codex config profiles, and running OpenRouter models
under `cline` / `opencode`, where pinning the upstream endpoint is the largest cost lever
on a week-long run.

Everything here is optional. A run with no config at all uses `claude` on `sonnet`; you
come here when you want a different CLI, a cheaper tier for the easy nodes, or a model
the harness would not have picked.

For what workhorse is and how to start a run, see
[README.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/README.md). For
the resilience and timeout knobs, see
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

## Choosing the agent CLI backend

The controller drives one agent CLI per run, behind a backend port
(`workhorse/runner/backends/` — `__init__.py` declares `AgentBackend`, each CLI owns
a sibling module, `registry.py` maps a name to one). The CLI is chosen **per-run**
(the *model* is still per-node — see below):

```bash
workhorse-<name> run                      # claude (default)
workhorse-<name> run --cli codex
workhorse-<name> run --cli copilot
workhorse-<name> run --cli cline          # OpenRouter-native
workhorse-<name> run --cli opencode       # OpenRouter-native
# Equivalently, set the AGENT_CLI={claude,codex,copilot,cline,opencode} env var.
```

The backend default model is overridable per run with the `AGENT_MODEL` env var.
Workflows can request an abstract `power` tier per agent turn; your user-wide config
maps that tier to concrete backend model/effort settings. Turns with no `power=` (and
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
| `cline` | `cline --json` | — (node names it) | no — ladder reframes on overflow |
| `opencode` | `opencode run --format json` | — (node names it) | no — ladder reframes on overflow |

For running OpenRouter models (e.g. MiMo) on `cline` / `opencode`, see
[OpenRouter models](#openrouter-models--cline-and-opencode) below.

### Node power selection

An agent turn's optional `power=` argument is not a model name — it is an abstract tier
resolved through the shared config file for the active backend (see [Config file
location](#config-file-location) below):

```python
verdict = self.agent("prompts/lead-review.md", returns=Verdict, power="high")
```

**The tier name is an opaque string.** Workhorse validates nothing about it: the tiers
that exist are whatever `[power.<tier>.<backend>]` tables the operator's config declares,
so a workflow with a rung of its own — `verdict`, `cheap-bulk`, whatever fits its shape —
just names it and has the operator map it. A tier no table matches falls through to
`[default.<backend>]`, so an unmapped or misspelled tier quietly runs at the backend
default rather than failing the run. That is the trade for the openness, and it is worth
knowing when a workflow seems to be ignoring its tiering.

The convention the shipped workflows follow, cheapest first, is `low` / `medium` / `high`
/ `smart` / `extra-smart`, and following it means one config serves every workflow. The
top of that ladder is three rungs because "the strongest thing available" is not one
decision. `high` is the good model for real work — the tier most turns in a working
workflow want. `smart` is frontier reasoning, for the handful of turns whose judgment the
whole run rests on. `extra-smart` is the premium model, chosen knowing what it costs.
Collapsing those into one rung forces the operator to price every `high` turn at the rate
of the rarest one, which in practice means the top tier gets configured down until it is
no longer a top tier.

Example config:

```toml
[power.low.claude]
model = "haiku"
effort = "low"

[power.medium.claude]
model = "sonnet"
effort = "medium"

[power.high.claude]
model = "sonnet"
effort = "high"

[power.smart.claude]
model = "opus"
effort = "high"

[power.extra-smart.claude]
model = "fable"
effort = "medium"

[power.high.codex]
model = "@gpt-5.5"
effort = "high"

[power.high.opencode]
model = "openai/gpt-5.5"
effort = "high"
```

A tier you leave unmapped for a backend falls through to `[default.<backend>]`, so a
workflow may name `extra-smart` on a backend where you have not defined it without
failing the run — it simply runs at that backend's default.

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

Model resolution order per turn: `power.<tier>.<backend>` mapping → `AGENT_MODEL` /
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
approach (the 1M-token OpenRouter endpoints in [OpenRouter models](#openrouter-models--cline-and-opencode)),
that is pure cost with nothing gained. Turning it off is right for *those* runs and
wrong for a run against a 272k window, which is exactly why it is scoped to the
harness config rather than set globally in `~/.config/opencode/opencode.jsonc`.

Scoped per **harness**, not per power tier: a knob like that is a property of the
CLI, not of how hard a node is thinking. (And unlike `model`/`effort`, which resolve
by "first layer that names one wins", an env table would want to *merge* across
layers — so a second layer would be a different resolution rule, not more of the
same one.)

Inspect or set config with **farrier**, which owns the shared config file — workhorse
is a library and ships no command of its own:

```bash
farrier config show                        # print all config keys
farrier config show power.high.claude      # print one value
farrier config set-library ~/path/to/lib   # set the overlay library path
farrier config set-stablemate ~/path/to/sm # set the stablemate checkout path
farrier config set-base ~/path/to/base     # set the base library content path
farrier config list                        # list all config keys (power table friendly)
farrier config get power.high.claude       # get one key
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
if every tool agrees on them — with a file per tool, each tool's own `config set-base`
wrote to a different place and they could silently disagree. The
pre-unification per-tool files (`~/.config/workhorse`, `~/.config/farrier`) are still
read when the shared one is absent, and the first write folds them into it, so an
existing setup keeps working with no migration step.

#### Config schema version

The file carries a `config_version`. workhorse and farrier are installed separately and
versioned independently, so the file — not the code — is where they are kept in step:

| Situation | Behavior |
|---|---|
| Config is newer than this build | `config set-*` **refuses** (exit 1). Upgrade the tool. |
| Config is older than this build | Migrated forward on the next write; the old file is kept as `config.toml.v<n>.bak`. |
| Reading a newer config | Succeeds, logs a warning. |

Reads deliberately never raise: `power` is re-read per node, so a hard failure would kill
an unattended run mid-flight because some other tool was upgraded. Writes are the guard,
because a writer that does not understand a key drops it — which is exactly the bug that
made this one file in the first place.

#### Initial setup

The library paths are shared with `farrier`, which installs the skill and prompt
content a workflow's prompts reference. Workhorse does not resolve workflows through
them — they are one config file so both tools agree on where that content lives:

```bash
farrier config set-library ~/path/to/your/prompt-library
# Optionally, also set the stablemate checkout (where its base-library is found):
farrier config set-stablemate ~/path/to/stablemate
```

Then verify:

```bash
farrier config show
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

## OpenRouter models — `cline` and `opencode`

To run a workflow on an OpenRouter model — e.g. the MiMo-V2.5 experiment — drive
the run with an **OpenRouter-native backend** and map the desired `power` tier to an
`openrouter/<slug>` model for that backend. Both `cline` and `opencode` speak plain
chat-completions, so they reach OpenRouter **directly, with no proxy** (unlike
codex's Responses API, which needs one). Export your key once and pick the backend:

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
workhorse-<name> run --cli opencode   # or: --cli cline
```

Point the power tier at the model in your config, so the same workflow still runs
natively under `--cli claude`:

```toml
[power.high.opencode]
model = "openrouter/xiaomi/mimo-v2.5"
```

| Trait | `cline` | `opencode` |
|---|---|---|
| Invocation | `cline --json` (agentic loop) | `opencode run --format json` (agentic loop) |
| Output | NDJSON events | NDJSON events |
| Session resume | by id (`--id`) | by id (`--session`) |
| Reasoning effort | `--thinking` (none/low/medium/high/xhigh) | `--variant` (minimal/high/max) |
| Usage reported | tokens, cache split, cost and duration, in one terminal event | tokens and cost, summed across per-step events |

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
- **cline** reaches OpenRouter through its own provider settings, so the same
  `provider` routing object belongs there rather than in any workhorse config. Set it
  in cline's settings before the run; workhorse only names the `openrouter/<slug>`
  model.

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

…or for a single run, `OPENCODE_DISABLE_AUTOCOMPACT=1 workhorse-<name> run --cli
opencode`. Either way it is scoped to the harness, which is the point: do **not** set
`"compaction": {"auto": false}` in `opencode.jsonc`, because that key is global with
no per-provider scope and would also disable compaction for models that run close to
their ceiling and rely on it. See
[Per-harness environment](#per-harness-environment-harnessbackendenv). Note the ladder still covers a
genuine overflow either way — opencode exposes no in-place `/compact`
(`supports_compaction = False`), so workhorse reframes the node in a fresh session
rather than compacting.

