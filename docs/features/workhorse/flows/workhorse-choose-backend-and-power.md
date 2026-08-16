---
type: flow
slug: workhorse-choose-backend-and-power
title: Choose the agent CLI backend and power tier
---
# Choose the agent CLI backend and power tier

How an operator points a run at a different agent harness and gives its nodes a *relative*
performance tier instead of a hardcoded model name: hand-edit the `[power.<tier>.<backend>]` table
in the [shared config file](../concepts/config.md), pick the harness for the run with
[`workhorse-<name> run`](../workhorse.md#run)'s `--cli`, and let each [agent
node](../workflow-format.md#the-agent-turn)'s `power:` resolve through that table for whichever
[AgentBackend](../concepts/agent-backend.md) got selected via
[`get_backend`](../concepts/get-backend.md). The same workflow — same `power="high"` on a turn —
thus runs against `opus` under `--cli claude` or `@gpt-5.5` under `--cli codex` with no edit to the
workflow itself. A second, independent axis picks *which set* of those mappings applies: a
[`[profiles.<name>]`](../concepts/config.md#profiles) table names a whole alternative `power` /
`default` set, selected per run with `--profile` (or swapped mid-run with `control switch-profile`),
so pointing one run at cheaper models no longer means editing the file every other run shares.

- start: an installed workflow whose `workhorse-<name>` command is on `PATH`, a config file
  (possibly empty — no `library_dir`/`power`
  table yet required) and a workflow whose [agent turns](../workflow-format.md#the-agent-turn)
  carry an optional [`power`](../workflow-format.md#power) tier — an opaque string, whose
  meaning is whatever the operator's config maps it to (the shipped workflows use
  `low`/`medium`/`high`/`smart`/`extra-smart`, cheapest first; default unset).
- steps:
  1. **Populate the power table.** No command writes the nested `power` table
     — [`write_config_key`](../concepts/config.md#write_config_key) sets one top-level key at a
     time (`library_dir`, `stablemate_dir`, `base_dir`); it preserves nested tables it did not
     write, but it has no path syntax for reaching into one. An operator instead edits the
     [config file](../concepts/config.md) directly at its
     [resolved path](../concepts/config.md#location) (`$STABLEMATE_CONFIG`, else the
     platform default), adding one `[power.<tier>.<backend>]` section per tier/backend pair it
     wants to override, each with `model = "…"` and/or `effort = "…"` string keys, e.g.:
     ```toml
     [power.high.claude]
     model = "opus"
     effort = "high"

     [power.high.codex]
     model = "@gpt-5.5"
     effort = "high"
     ```
     A tier/backend pair with no section is not an error — it just leaves that combination
     unresolved (step 7 below falls through to the backend's own default). A top-level
     `[default.<backend>]` section (same `model`/`effort` keys) additionally pins a per-backend
     fallback for nodes with no `power:` at all or tiers left unmapped — without it those nodes
     run on whatever model the harness auto-picks:
     ```toml
     [default.opencode]
     model = "openai/gpt-5.5"
     effort = "high"
     ```
  2. *(optional)* **Name a whole alternative set of those tables, as a profile.** Editing the
     tables above moves *every* run on the machine, including the six-day one already going, and
     leaves no record of what a finished run actually bought. A
     [`[profiles.<name>]`](../concepts/config.md#profiles) table holds its own `power`, `default`
     and `default_cli` under one name, selected per run in step 5:
     ```toml
     [profiles.cheap.power.high.claude]
     model = "sonnet"

     [profiles.cheap.default.claude]
     model = "haiku"
     ```
     A profile **replaces** the top-level tables rather than layering over them — nothing outside
     it is inherited — because power tiers are opaque strings and "the profile did not mention
     `smart`, so it means the machine's `smart`" is a guess the config cannot state. What is *not*
     a model set stays outside and still applies: `[harness.<backend>].env`, `library_dir`,
     `base_dir`, `stablemate_dir`. There is no writer for this table either, for the same reason as
     step 1's.
  3. *(optional)* **Confirm what's configured.** [`farrier config
     show`](../../farrier/farrier.md#config) prints every stored key as `key=value` lines via
     [`load_config`](../concepts/config.md#load_config) — flat keys only, so the `power` table is
     read back by opening the file. `farrier config show --profile <name>` is the exception: it
     narrows to one profile and flattens it to one dotted line per leaf
     (`power.high.claude.model=sonnet`), so two profiles diff against each other line by line.
     `farrier config --config <path> show` asks the same question of a file that is not this
     machine's. None of it mutates anything: this step is read-only verification of steps 1–2.
  4. **Pick the harness for the run.** [`workhorse-<name> run --cli
     <backend>`](../workhorse.md#run) (else the `AGENT_CLI` env var, else `claude`) sets `AGENT_CLI`
     and calls [`get_backend`](../concepts/get-backend.md#contract) once, eagerly — an unknown
     `<backend>` prints an error listing the valid keys and exits `1` before any node runs, rather
     than failing mid-run. `<backend>` ∈ `claude` (default) · `codex` · `copilot` · `cline` · `opencode`,
     each the registry key of one [AgentBackend](../concepts/agent-backend.md) implementation.
     `get_backend` caches one stateless instance per key, reused for every node of the run.
  5. **Point the run at one named set of models.** `run --profile <name>` selects a
     [`[profiles.<name>]`](../concepts/config.md#profiles) table for this run and no other;
     `run --config <path>` swaps the whole config *file* instead, by writing the resolved path into
     `$STABLEMATE_CONFIG` so every later reader and subprocess resolves the same one. The two are
     independent of `--cli`: a profile carries a `default_cli`, so the profile is selected *before*
     the backend and the ladder is `--cli` > `AGENT_CLI` > the profile's `default_cli` > the top
     level's > `claude`. Both are validated eagerly at the boundary — an unknown profile name, a
     `--config` path that is not a file, or a profile that maps no model for the chosen backend
     ([`profile_has_backend`](../concepts/config.md#profiles), the two-axes misuse) each
     print and exit `1` before node one, and the profile check runs under `--dry-run` too, that
     being its point. The chosen name is recorded in
     [`run.json`](../run-artifacts.md#runjson)'s `profile` (alongside an informational
     `profile_config` snapshot) and stamped on the run's root span as `workhorse.profile`, so a
     flagless `--resume-run` — and the re-exec behind `control switch-cli` — re-applies the same
     set rather than silently falling back to the top level.
  6. **Run the machine.** [`drive`](../concepts/pyflow-driver.md) walks the states; each
     [agent turn](../workflow-format.md#the-agent-turn) a state reaches is driven by
     [`AgentRunner.run`](../concepts/run-agent.md).
  7. **Resolve this turn's power to a concrete model/effort.** Inside `AgentRunner.run`'s setup
     (before the resilience ladder), `_resolve_power_settings(node.power, backend.name,
     model_override, profile)` loads the config, narrows it through
     [`select_profile`](../concepts/config.md#profiles) when a profile is set, and maps the
     turn's `power` tier through [`resolve_power`](../concepts/config.md#resolve_power) against the
     *same* `backend.name` chosen in step 4 — so `power.high.claude` and `power.high.codex` are
     independent entries and only the one matching the run's active backend applies. That load and
     narrow happen **per turn**, not once at startup, which is what lets step 9 reach the next turn:
     - `power` unset/`None`/`""` short-circuits to an empty `PowerMapping` (no override) —
       `resolve_power` is never consulted.
     - otherwise looks up `power.<power>.<backend>`, falling back to `power.<power>.default` if no
       backend-specific section exists; any missing step (no `power` table at all, no such tier, no
       matching backend/default section) yields an empty mapping rather than raising.
     - the resolved `model` then falls through, in order, to `AGENT_MODEL`, then
       `AGENT_CLAUDE_MODEL` (both env vars, resolved once at the CLI boundary and handed down),
       then the `[default.<backend>]` table of whichever config the step above narrowed to via
       [`resolve_backend_default`](../concepts/config.md#resolve_backend_default); `effort` falls
       through to that same table directly (it has no env override).
     - back in `AgentRunner.run`, a still-unset `model` finally falls through to `backend.default_model`
       (`sonnet` for claude; `None` for the others, which leaves the harness to pick) so a node
       without any configuration still runs.
  8. **Drive the turn with the resolved settings.** `AgentRunner.run` calls
     [`AgentBackend.run_turn`](../concepts/agent-backend.md#contract)`(prompt, session_id_path,
     model=model, effort=node_effort, …)` on the step-4 backend instance; each concrete backend
     ([claude](../concepts/claude-backend.md), [codex](../concepts/codex-backend.md),
     [copilot](../concepts/copilot-backend.md), [cline](../concepts/cline-backend.md),
     [opencode](../concepts/opencode-backend.md)) translates `model`/`effort` into its own CLI
     flags.
  9. *(optional)* **Move a run that is already going onto another set.** `workhorse-<name> control
     --run <id> switch-profile <name>` applies in-process at the next node boundary: the
     run keeps its pid, its root span and its wall-clock budget, and because step 7 re-loads and
     re-narrows the config every turn, the new set reaches the next turn with no reload and no
     restart. `run.json` keeps naming the profile the run was *launched* with, so a later
     `--core` re-exec carries the switched-to name in its argv rather than reading the record and
     resolving from the set the operator switched away from.
- end: the node's turn runs against the model/effort named by the `power.<tier>.<backend>` entry of
  the config the run selected — the top-level tables, or one `[profiles.<name>]` table replacing
  them — for the run's chosen `--cli`. The same workflow reruns unchanged under a different `--cli`
  *or* a different `--profile`, each node's relative "how much power" intent carrying over via a
  fresh tier/backend lookup rather than a model name baked into the workflow; and the name of the
  set it ran under survives on `run.json` and on the root span's `workhorse.profile`, so a finished
  run can still answer which models it bought after the config has moved on.
- verify: `workhorse/tests/test_model_resolution.py`
- verify: `workhorse/tests/test_run_options.py`

## Missing element noticed

No command writes a `power.<tier>.<backend>` or `[profiles.<name>]` entry — [`farrier
config`](../../farrier/farrier.md#config)'s `set-library`/`set-stablemate`/`set-base` each set one
flat top-level key, and plain `show` reads flat keys back — so populating either table is a manual
TOML edit, not a CLI round-trip. Reading is now half-solved (`show --profile <name>` flattens one
profile's nested tables to dotted lines), but writing is not: worth a `farrier config set
power.<tier>.<backend> model=… effort=…` command with the same dotted-path syntax the reader
already accepts, and out of scope here (this item documents current behavior, not a proposal).
