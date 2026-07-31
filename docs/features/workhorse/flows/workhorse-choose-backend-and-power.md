---
type: flow
slug: workhorse-choose-backend-and-power
title: Choose the agent CLI backend and power tier
---
# Choose the agent CLI backend and power tier

How an operator points a run at a different agent harness and gives its nodes a *relative*
performance tier instead of a hardcoded model name: hand-edit the `[power.<tier>.<backend>]` table
in the [workhorse config file](../concepts/config.md), pick the harness for the run with
[`workhorse run`](../workhorse.md#run)'s `--cli`, and let each [agent
node](../workflow-format.md#the-agent-turn)'s `power:` resolve through that table for whichever
[AgentBackend](../concepts/agent-backend.md) got selected via
[`get_backend`](../concepts/get-backend.md). The same workflow — same `power="high"` on a turn —
thus runs against `opus` under `--cli claude` or a `@gpt-5.5` profile under `--cli codex` with no
edit to the workflow itself.

- start: a `workhorse` install with a config file (possibly empty — no `library_dir`/`power`
  table yet required) and a workflow whose [agent turns](../workflow-format.md#the-agent-turn)
  carry an optional [`power`](../workflow-format.md#power) tier (`low`/`medium`/`high`, default
  unset).
- steps:
  1. **Populate the power table.** There is no `workhorse config set` for the nested `power` table
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
     unresolved (step 5 below falls through to the backend's own default). A top-level
     `[default.<backend>]` section (same `model`/`effort` keys) additionally pins a per-backend
     fallback for nodes with no `power:` at all or tiers left unmapped — without it those nodes
     run on whatever model the harness auto-picks:
     ```toml
     [default.opencode]
     model = "openai/gpt-5.5"
     effort = "high"
     ```
  2. *(optional)* **Confirm what's configured.** [`workhorse config
     list`](../workhorse.md#config) prints the whole loaded TOML (the power table in full, as
     indented JSON) via [`load_config`](../concepts/config.md#load_config); [`workhorse config get
     power.<tier>.<backend>`](../workhorse.md#config) prints one resolved value via
     [`get_config_value`](../concepts/config.md#get_config_value) (silently empty if that dot-path
     doesn't resolve, unlike `show`'s hard error on a missing top-level key). Neither command
     mutates the file — this step is read-only verification of step 1.
  3. **Pick the harness for the run.** [`workhorse run <workflow> --cli
     <name>`](../workhorse.md#run) (else the `AGENT_CLI` env var, else `claude`) sets `AGENT_CLI`
     and calls [`get_backend`](../concepts/get-backend.md#contract) once, eagerly — an unknown
     `<name>` prints an error listing the valid keys and exits `1` before any node runs, rather than
     failing mid-run. `<name>` ∈ `claude` (default) · `codex` · `copilot` · `aider` · `opencode`,
     each the registry key of one [AgentBackend](../concepts/agent-backend.md) implementation.
     `get_backend` caches one stateless instance per key, reused for every node of the run.
  4. **Run the machine.** [`drive`](../concepts/pyflow-driver.md) walks the states; each
     [agent turn](../workflow-format.md#the-agent-turn) a state reaches is driven by
     [`AgentRunner.run`](../concepts/run-agent.md).
  5. **Resolve this turn's power to a concrete model/effort.** Inside `AgentRunner.run`'s setup (before
     the resilience ladder), `_resolve_power_settings(node.power, backend.name, os.environ)` maps
     the turn's `power` tier through [`resolve_power`](../concepts/config.md#resolve_power) against
     the *same* `backend.name` chosen in step 3 — so `power.high.claude` and `power.high.codex` are
     independent entries and only the one matching the run's active backend applies:
     - `power` unset/`None`/`""` short-circuits to an empty `PowerMapping` (no override) —
       `resolve_power` is never consulted.
     - otherwise looks up `power.<power>.<backend>`, falling back to `power.<power>.default` if no
       backend-specific section exists; any missing step (no `power` table at all, no such tier, no
       matching backend/default section) yields an empty mapping rather than raising.
     - the resolved `model` then falls through, in order, to `AGENT_MODEL`, then
       `AGENT_CLAUDE_MODEL` (both env vars), then the config's `[default.<backend>]` table via
       [`resolve_backend_default`](../concepts/config.md#resolve_backend_default); `effort` falls
       through to that same table directly (it has no env override).
     - back in `AgentRunner.run`, a still-unset `model` finally falls through to `backend.default_model`
       (`sonnet` for claude; `None` for the others, which leaves the harness to pick) so a node
       without any configuration still runs.
  6. **Drive the turn with the resolved settings.** `AgentRunner.run` calls
     [`AgentBackend.run_turn`](../concepts/agent-backend.md#contract)`(prompt, session_id_path,
     model=model, effort=node_effort, …)` on the step-3 backend instance; each concrete backend
     ([claude](../concepts/claude-backend.md), [codex](../concepts/codex-backend.md),
     [copilot](../concepts/copilot-backend.md), [aider](../concepts/aider-backend.md),
     [opencode](../concepts/opencode-backend.md)) translates `model`/`effort` into its own CLI
     flags.
- end: the node's turn runs against the model/effort named by the config's
  `power.<tier>.<backend>` entry for the run's chosen `--cli` — the same workflow reruns unchanged
  under a different `--cli` and each node's relative "how much power" intent carries over via a
  fresh tier/backend lookup, rather than a model name baked into the workflow.
- verify: `workhorse/tests/test_model_resolution.py`

## Missing element noticed

`workhorse config` has no subcommand to *write* a `power.<tier>.<backend>` entry (only
`show`/`get`/`list` read it back; `set-library`/`set-stablemate`/`set-base` each set one flat
top-level key) — populating the power table is a manual TOML edit, not a CLI round-trip. Worth a
`workhorse config set power.<tier>.<backend> model=… effort=…` command, but out of scope here
(this item documents current behavior, not a proposal).
