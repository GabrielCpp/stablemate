# Authoring a `workflow.yaml`

Complete reference for writing workhorse workflows. A workflow is a YAML file
describing a directed graph of **nodes**; workhorse walks it node-by-node,
checkpointing after each step so a run can resume exactly where it stopped.

For the runtime resilience knobs (retries, reframes, cap waits, timeouts as
environment variables) see [GUARDRAILS.md](GUARDRAILS.md). This document covers
the **workflow file schema** itself.

---

## 1. Top-level structure

```yaml
name: my-workflow        # optional — defaults to the YAML filename stem
start: first             # REQUIRED — id of the entry node
vars:                    # optional — initial context (CLI --params overrides on fresh start)
  subject: "the topic"
  max_retries: 3
nodes:                   # REQUIRED — the list of nodes (each needs a unique id + type)
  - id: first
    type: agent
    ...
```

| Key | Type | Required | Meaning |
|-----|------|----------|---------|
| `name` | string | no | Run/log name; used in the run directory `<name>-<run-id>`. Defaults to the file stem. |
| `start` | string | **yes** | Id of the first node. Must exist in `nodes`. |
| `vars` | mapping | no | Initial context variables. Merged before the first node; `--params` overrides them on a fresh start (not on resume). |
| `nodes` | list | **yes** | Node definitions. Every node has a unique `id` and a `type`. |

**Validation at load:** `start` must reference a real node, and every `next` /
branch target must resolve to an existing node, or the workflow is rejected.

Every workflow must contain at least one `terminal` or `fail` node (the only
node types allowed to have no `next`).

---

## 2. Node types

All nodes share two fields: `id` (unique within the workflow) and `type`
(`agent` | `script` | `branch` | `terminal` | `fail`).

### 2.1 `agent` — run the assistant

Renders a prompt template and sends it to the active agent CLI (Claude / Codex /
Copilot), then extracts JSON outputs from the response.

```yaml
- id: plan
  type: agent
  prompt: prompts/plan.md      # Jinja2 template, path relative to the workflow dir
  args:                        # rendered Jinja strings, merged into the prompt context
    story_path: "{{ story_path }}"
    spec_dir: "{{ spec_dir }}"
  outputs:                     # JSON keys to capture from the response
    - key: plan_result
      default: { status: blocked }   # emitted if the node exhausts all retries
  power: high                  # optional abstract tier resolved through user config
  timeout: 1800                # optional wall-clock budget in seconds (default 3600)
  next: review_plan            # REQUIRED for agent nodes
```

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `prompt` | string | **yes** | Path to a Jinja2 template (`.md`/`.txt`), relative to the workflow dir (or absolute). |
| `args` | map<str,str> | no | Jinja string values rendered against the context, then merged into the prompt context. Lets you parameterize a prompt without editing the template. |
| `outputs` | list of [OutputSpec](#23-outputspec) | no | JSON keys to extract from the response. Missing keys trigger the resilience ladder. |
| `power` | `low` \| `medium` \| `high` | no | Abstract capacity tier. Resolved through `~/.config/workhorse/config.toml` at `power.<tier>.<backend>` to concrete `model`/`effort`; missing config leaves model/effort unset so the backend default or `AGENT_MODEL` applies. |
| `timeout` | number | no | Wall-clock seconds for the turn. Surfaced to the prompt as `node_timeout_s` / `node_timeout_min`. Default **3600** (1 hour); `0`/null → engine default. |
| `next` | string | **yes** | Node to advance to. Agent nodes may **not** be terminal. |

**Output extraction.** Strict first: the response is scanned for a fenced
```` ```json … ``` ```` block, then the first top-level `{…}` object, parsed
with the stdlib. If that doesn't yield an object carrying every declared
`outputs` key, a tolerant `json-repair` pass recovers the object — fixing
trailing commas, single quotes, comments, and truncated/unclosed braces, and
preferring the object with the declared keys when the response embeds several
(an example plus the real answer). Only if no object can be recovered, or a
declared key is still missing, is it an `OutputParseError` (which then climbs
the resilience ladder). With no `outputs`, nothing is captured (the agent may
still print JSON).

**Resilience (summary; full detail in [GUARDRAILS.md](GUARDRAILS.md)).** On
failure workhorse climbs a ladder rather than crashing: transient retries
(rate-limit/network) → wait-for-cap-reset → output-parse retries → compact &
continue (context overflow) → reframe in a fresh session → finally emit the
declared `default` outputs and advance to `next`. Each node runs as a fresh
prompt in a clean session; conversations are not chained between nodes.

### 2.2 `script` — run a shell/Python script

Runs a script with the workflow dir as cwd, passes rendered args as positional
arguments, and parses its **stdout as a single JSON object**.

```yaml
- id: init_counter
  type: script
  script: scripts/init_counter.py    # .py → python3, .sh/.bash → bash, else run directly
  args:
    - "{{ story_path }}"
  outputs:
    - key: rework_count
      default: { value: 0 }
  next: plan                         # REQUIRED for script nodes
```

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `script` | string | **yes** | Path relative to the workflow dir. |
| `args` | list<str> | no | Jinja strings rendered against the context, passed as positional args. |
| `outputs` | list of OutputSpec | no | Keys to extract from the script's JSON stdout. |
| `next` | string | **yes** | Next node. Script nodes may **not** be terminal. |

A non-zero exit, non-JSON stdout, or a missing declared key raises an error.

### 2.3 OutputSpec

Each entry in an `outputs` list:

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `key` | string | **yes** | JSON key to extract from the response/stdout and merge into the context. |
| `default` | any | no | Value emitted if the node exhausts all retries/reframes. Any JSON type. Unset → `null`. Choose a value that keeps downstream branches safe (e.g. a `status` that routes to a recovery path). |

```yaml
outputs:
  - key: decision
    default: needs_rework      # branch-safe fallback
  - key: review
    default: { status: auto_approved }
  - key: notes                 # no default → null on failure
```

### 2.4 `branch` — route on a context value

Looks up a dot-path in the context and routes accordingly.

```yaml
- id: decide_plan
  type: branch
  path: review_plan_result.status   # dot-path into the context
  cases:                            # exact (string) equality, checked first
    approved: implement
    needs_rework: refine_plan
    blocked: await_operator
  conditions:                       # ordered comparisons, checked if no case matched
    - op: ">="
      value: "3"
      next: give_up
  default: await_operator           # used if path unresolved OR nothing matched
```

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `path` | string | **yes** | Dot-path (e.g. `result.status`, `counter.value`) resolved against the context. |
| `cases` | map<str,str> | no | value (as string) → next node. Evaluated first. |
| `conditions` | list of [BranchCondition](#branchcondition) | no | Ordered comparisons evaluated when no case matches; first true wins. |
| `default` | string | no | Fallback when the path can't be resolved or nothing matches. Without it, an unresolved/unmatched branch raises an error. |

#### BranchCondition

| Field | Type | Meaning |
|-------|------|---------|
| `op` | `==` `!=` `<` `>` `<=` `>=` | Comparison. `<`,`>`,`<=`,`>=` coerce both sides to float; `==`/`!=` compare as strings. |
| `value` | string | Right-hand side (coerced to float for numeric ops). |
| `next` | string | Target node if the condition holds. |

> Branch case/condition values are literal strings — you cannot put a Jinja
> expression in a `cases:` key or a `value:`. Compute the value upstream and
> branch on the produced field.

### 2.5 `terminal` / `fail` — end the run

```yaml
- id: done
  type: terminal      # success — exit code 0
- id: qa_failed
  type: fail          # failure — exit code 1 (still a clean, resumable stop)
```

Both take only `id` (and `type`). They have no `next`.

---

## 3. Context & templating

### 3.1 What's in the context

The context is a single key→value map that flows through the run:

1. Seeded from `vars`, then overlaid by `--params` / `--params-file` on a fresh start.
2. Each node merges its extracted `outputs` into the context, so downstream
   templates can read `{{ upstream_key.field }}`.
3. Persisted in the checkpoint before each node; restored verbatim on resume
   (params are **not** re-applied on resume).

### 3.2 Template rendering

Prompts and `args` are Jinja2 templates rendered with a **resilient undefined**:
a missing variable or a bad traversal renders as an empty string (and logs a
warning) rather than crashing. This keeps a prompt usable even when an optional
upstream output is absent — but it also means a typo silently renders empty, so
check the warnings.

Variables available inside a prompt:

| Variable | Meaning |
|----------|---------|
| workflow `vars` | Everything declared in `vars:` (and `--params` overrides). |
| prior node outputs | Any `outputs` keys merged by earlier nodes, e.g. `{{ plan_result.status }}`. |
| rendered `args` | Each `args` entry is rendered first, then exposed by its key. |
| `node_timeout_s` | This node's effective budget in seconds (int). |
| `node_timeout_min` | Same budget in minutes (rounded) — e.g. `You have ~{{ node_timeout_min }} min`. |

`args` values are rendered against the context **without** `node_timeout_*`; the
prompt body is rendered against context **plus** args and the timeout values.

### 3.3 Dot-paths (branch `path:`)

`path: a.b.c` resolves `context["a"]["b"]["c"]`. A missing segment or a
non-dict traversal routes to the branch `default` (with a warning) if one is
set, otherwise raises.

---

## 4. Running a workflow

```bash
# --workflow takes a path OR a bare library name (e.g. `author`); run from the
# repo dir so artifacts default to ./.agents/runs.
workhorse --workflow author \
  [--runs-dir DIR] [--run-id ID] \
  [--params '{"story_path":"docs/…"}'] [--params-file params.json] \
  [--cli claude|codex|copilot|aider|opencode] \
  [--resume-run ID|PATH | --resume-latest]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--workflow` | — (required) | Path to a workflow file, **or** a bare workflow name (e.g. `author`) resolved from the configured prompt library as `<library_dir>/workflows/<name>/workflow.yaml`. Library dir = `$WORKHORSE_LIBRARY_DIR` or `library_dir` in `~/.config/farrier/config.toml`. |
| `--runs-dir` | `<cwd>/.agents/runs` | Where run artifacts are written. Defaults to `.agents/runs` under the directory you launch workhorse from (not the workflow's dir). |
| `--run-id` | `default` | Stable id; run dir is `<name>-<run-id>`. Use distinct ids to keep parallel runs apart. |
| `--params` | — | Inline JSON object merged into the starting context (overrides `vars`). |
| `--params-file` | — | JSON file of params; inline `--params` wins on conflict. |
| `--cli` | `claude` (or `$AGENT_CLI`) | Agent backend: `claude`, `codex`, `copilot`, `aider`, or `opencode`. For OpenRouter models (e.g. MiMo) use `aider`/`opencode` and an `openrouter/<slug>` node model — see the README's "OpenRouter models". |
| `--resume-run` / `--resume-latest` | — | Manually resume a specific / the latest unfinished run. |

**Auto-resume.** By default each `(workflow, run-id)` maps to one stable run
dir. If it already holds a checkpoint, the run resumes from it; otherwise it
starts fresh. So re-invoking the same command after an interruption just
continues — no flags needed.

Run artifacts (per run dir): `run.json` (start/end/terminal state),
`checkpoint.json` (current node + context, for resume), `context.json` (final
context), and per-node folders with the rendered `prompt.md`, captured
`output.json`, and `context_after.json`.

---

## 5. Minimal complete example

```yaml
name: example
start: step
vars:
  subject: "the Fibonacci sequence"

nodes:
  - id: step
    type: agent
    prompt: prompts/step.md
    args:
      subject: "{{ subject }}"
    outputs:
      - key: result
        default: { status: error }
    next: decide

  - id: decide
    type: branch
    path: result.status
    cases:
      ok: done
    default: failed

  - id: done
    type: terminal
  - id: failed
    type: fail
```

See [`../../`](https://github.com/GabrielCpp/stablemate) and the prompt-library
workflows (e.g. `hello-world`, `coder`) for larger, real examples: tiered models
per stage, CI gates, rework loops with numeric `conditions`, and operator-gated
pauses that resume cleanly.
