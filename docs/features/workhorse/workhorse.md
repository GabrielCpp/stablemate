---
type: cli
slug: workhorse
title: workhorse — fail-soft runner for YAML agent workflows
---
# workhorse

Walks a directed graph of nodes defined by a [workflow](concepts/workflow.md) — on disk the
[workflow file format](workflow-format.md) — checkpointing after each node so a run resumes
exactly where it stopped, built to run unattended for days. The agent harness that drives a
run is an [AgentBackend](concepts/agent-backend.md), chosen per run via
[get_backend](concepts/get-backend.md) from the `--cli` flag.

- binary: `workhorse`
- code: `workhorse/workhorse/main.py::main`

**Exit codes:** a run exits `0` when it reaches a `terminal` node, `1` when it reaches a `fail`
node or dies unrecovered (see [workflow](concepts/workflow.md) execution); with no recognized
subcommand, a bare `workhorse [--workflow …]` is treated as `run`.

## Commands

### run
- usage: `workhorse run <workflow> [<flow>] [--params JSON]` (the default command)
- flags:
  - `--workflow <path>` — run a `workflow.yaml` by path instead of the positional name; equivalent to the positional form.
  - `--context-file <path>` — the per-repo farrier context manifest (JSON) that library prompts
    render against (template values, instruction/prompt path maps, selected-skills set). When
    omitted, auto-detected as `$AGENT_REPO_DIR/.agents/agents-context.$AGENT_CLI.json` then
    `$AGENT_REPO_DIR/.agents/agents-context.json`; if neither exists the run proceeds with an empty
    manifest. If given explicitly, the path must exist — a typo is a hard error.
  - `--params <json>` / `--params-file <path>` — override the workflow's [vars](workflow-format.md#vars) on a *fresh start*; ignored on resume.
  - `--cli <name>` — pick the agent harness for the run: selects an [AgentBackend](concepts/agent-backend.md) implementation via [get_backend](concepts/get-backend.md); `<name>` ∈ `claude` (default) · `codex` · `copilot` · `aider` · `opencode`.
  - `--runs-dir <dir>` — where run artifacts are written (default `<workflow-dir>/runs`).
  - `--run-id <id>` — name the stable run dir (`<workflow>-<id>`, default `default`); distinct ids keep parallel runs side by side.
  - `--resume-run <path-or-id>` / `--resume-latest` / `--no-cache` — mutually exclusive with each
    other. `--resume-run`/`--resume-latest` resume a checkpointed run instead of the default
    auto-resume-in-place. `--no-cache` deletes the stable run dir before starting (forcing a clean
    run from scratch) instead of resuming it.
- args:
  - `<workflow>` — the named [workflow](concepts/workflow.md) to run (resolved from the prompt library), or a path via `--workflow`. Required.
  - `<flow>` — optional: run one named [flow](workflow-format.md#flows) of that workflow standalone, as a re-entry point, instead of the whole graph.
- does:
  - run: resolve the [workflow](concepts/workflow.md), walk its graph checkpointing per node, write run artifacts
- code: `workhorse/workhorse/main.py::_run_run`

`workhorse run coder qa --params '{"story":"CASE-1234"}'` runs the coder workflow's `qa`
flow standalone.

### test
- usage: `workhorse test <workflow_dir> [-k FILTER]`
- flags:
  - `-k <filter>` — a pytest `-k` expression selecting tests by name substring.
- args:
  - `<workflow_dir>` — the workflow whose `tests/` directory to run.
- does:
  - run: run pytest from the workflow's `tests/` directory
- code: `workhorse/workhorse/main.py::_run_test`

### dot
- usage: `workhorse dot --workflow <path> [--pin K=V] [--leaf NODE] [-o out.dot]`
- flags:
  - `--workflow <path>` — the [workflow](concepts/workflow.md) to render (required).
  - `--pin <K=V>` — pin a branch variable; matching branches collapse to their resolved edge and the now-unreachable subgraph is pruned. Repeatable — carves one mode's view out of a multi-mode graph.
  - `--leaf <node>` — render a node as a dead-end (suppress its out-edges) to cut a cross-view bridge not gated by a pinned branch. Repeatable.
  - `-o, --output <path>` — write DOT to a file instead of stdout.
- does:
  - run: render the [workflow](concepts/workflow.md) graph — described by the [workflow file format](workflow-format.md) — to Graphviz DOT
- code: `workhorse/workhorse/main.py::_run_dot`

### config
- usage: `workhorse config <show|get|list|set-library|set-stablemate> [args]`
- args:
  - `show [key]` — print all config keys as `key=value`, or one bare value; farrier-compatible.
  - `get <name>` — print one workhorse config value (e.g. `power.high.claude`).
  - `list` — print the loaded workhorse config (the power→model table).
  - `set-library <path>` — record the prompt-library dir in the shared home config.
  - `set-stablemate <path>` — record the stablemate checkout path (used as `CODER_WORKSPACE`).
- does:
  - run: read/write the shared workhorse/farrier home config (library path, power→model mappings)
- code: `workhorse/workhorse/main.py::_run_config`

Mirrors farrier's config interface so `agents.mk` and scripts can call either tool.

### version
- usage: `workhorse version`
- does:
  - run: print the installed `workhorse-agent` version
- code: `workhorse/workhorse/main.py::main`
