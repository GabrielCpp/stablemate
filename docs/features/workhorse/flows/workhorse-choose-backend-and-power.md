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
node](../workflow-format.md#agent)'s `power:` resolve through that table for whichever
[AgentBackend](../concepts/agent-backend.md) got selected via
[`get_backend`](../concepts/get-backend.md). The same `workflow.yaml` — same `power: high` on a
node — thus runs against `opus` under `--cli claude` or a `@gpt-5.5` profile under `--cli codex`
with no edit to the workflow itself.

- start: a `workhorse` install with a config file (possibly empty — no `library_dir`/`power`
  table yet required) and a workflow whose `agent` nodes carry an optional
  [`power:`](../workflow-format.md#agent) tier (`low`/`medium`/`high`, default unset).
- steps:
  1. **Populate the power table.** There is no `workhorse config set` for the nested `power` table
     — [`write_config_key`](../concepts/config.md#write_config_key) only round-trips flat top-level
     string keys (`library_dir`, `stablemate_dir`) and would corrupt a hand-written `[table]`
     section if pointed at one. An operator instead edits the [config file](../concepts/config.md)
     directly at its [resolved path](../concepts/config.md#location) (`$WORKHORSE_CONFIG`, else the
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
     unresolved (step 5 below falls through to the backend's own default).
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
  4. **Run the graph.** [Workflow execution](../concepts/workflow.md#execution) walks the nodes;
     each [`agent` node](../workflow-format.md#agent) is driven by [`run_agent`](../concepts/run-agent.md).
  5. **Resolve this node's power to a concrete model/effort.** Inside `run_agent`'s setup (before
     the resilience ladder), `_resolve_power_settings(node.power, backend.name, os.environ)` maps
     the node's `power:` tier through [`resolve_power`](../concepts/config.md#resolve_power) against
     the *same* `backend.name` chosen in step 3 — so `power.high.claude` and `power.high.codex` are
     independent entries and only the one matching the run's active backend applies:
     - `power` unset/`None`/`""` short-circuits to an empty `PowerMapping` (no override) —
       `resolve_power` is never consulted.
     - otherwise looks up `power.<power>.<backend>`, falling back to `power.<power>.default` if no
       backend-specific section exists; any missing step (no `power` table at all, no such tier, no
       matching backend/default section) yields an empty mapping rather than raising.
     - the resolved `model` then falls through, in order, to `AGENT_MODEL`, then
       `AGENT_CLAUDE_MODEL` (both env vars), if the config left it unset; `effort` has no env
       fallback — it just stays `None`.
     - back in `run_agent`, an still-unset `model` finally falls through to `backend.default_model`
       (e.g. `sonnet` for claude) so every node always has a concrete model.
  6. **Drive the turn with the resolved settings.** `run_agent` calls
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
`show`/`get`/`list` read it back; `set-library`/`set-stablemate` only ever touch flat top-level
keys) — populating the power table is a manual TOML edit, not a CLI round-trip. Worth a
`workhorse config set power.<tier>.<backend> model=… effort=…` command, but out of scope here
(this item documents current behavior, not a proposal).
