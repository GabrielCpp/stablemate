---
type: concept
slug: workflow
title: Workflow — a YAML-defined agent graph workhorse executes
---
# Workflow

A directed graph of nodes that [workhorse](../workhorse.md) executes **fail-soft**,
checkpointing after every node so a run resumes exactly where it stopped (built to run
unattended for days), each `agent` node driven by an [AgentBackend](agent-backend.md) harness.
Its on-disk shape is the [workflow file format](../workflow-format.md),
which [load_workflow](load-workflow.md) parses into the pydantic `Graph` modeled here;
[workhorse run](../workhorse.md#run) then walks it. A run's live state is a `WorkflowContext`
(`workhorse/workhorse/graph/context.py`) — a key→value bag with dot-path lookup for branches —
plus resumable run artifacts. The exhaustive field reference is
[the workflow file format](../workflow-format.md) (and `workhorse/docs/WORKFLOW.md`).

- code: `workhorse/workhorse/graph/nodes.py::Graph`

## Node types

Every node has an `id`, a `type`, and (except `terminal`/`fail`) a `next`. The set is fixed:

- **`agent`** — run an LLM against a Jinja `prompt` with rendered `args`, extracting the declared
  `outputs`. An optional `power` tier (low/medium/high) maps to a model via
  [workhorse config](../workhorse.md#config); the harness driving it is an
  [AgentBackend](agent-backend.md). The retry → reframe → default resilience ladder lives here.
- **`script`** — run a shell/Python script, capturing one JSON object from stdout as its
  `outputs`. Receives the workflow's `env` (below) in its subprocess environment.
- **`branch`** — route to a `next` by matching a context dot-`path` against `cases` (equality) or
  `conditions` (numeric `==`/`!=`/`<`/`>`/`<=`/`>=`), falling back to `default`.
- **`flow`** — call a named sub-graph from [flows](../workflow-format.md#flows) like a function
  (see [Flows](#flows) below).
- **`call`** — invoke a builtin `fn` with rendered `args`, capturing `outputs`; a lightweight
  step with no LLM and no subprocess.
- **`terminal`** / **`fail`** — end the run: exit 0 and exit 1 respectively.

## Flows

A **flow** is a named sub-graph — itself a full `Graph` — held in the workflow's
[flows](../workflow-format.md#flows) map. A `flow` node runs one like a function: the caller
passes `args`, and the flow executes against its **own isolated `vars`**, so parent state can't
silently leak in and the boundary stays explicit. A flow is also runnable standalone as a
re-entry point — [`workhorse run <workflow> <flow>`](../workhorse.md#run), e.g.
`workhorse run coder qa` — which is how a long workflow's phases (dev / review / qa) are launched
in isolation.

## Context — vars and env

- **`vars`** — the workflow's initial [context](../workflow-format.md#vars). A flow `var` with a
  null default is a **required** parameter (missing at launch → error); an empty-string default is
  **optional**. Overridden on a fresh start by [run](../workhorse.md#run)'s `--params` /
  `--params-file` (ignored on resume). Nodes read it in Jinja `args` and branch `path`s.
- **`env`** — workflow-level environment variables (Jinja-rendered from context) injected into
  **every `script` node**'s subprocess. A node's own `env` merges on top, so a node can override
  individual keys.

## Execution

The walk (`workhorse/workhorse/main.py::run`) is a single loop over nodes from `start`:

1. **Checkpoint** the current node id + context, so a crash here is resumable.
2. **Dispatch** by node type to its runner: `agent` → `runner/agent.py`, `script` →
   `runner/script.py`, `branch` → `runner/branch.py` (`flow`/`call`/`terminal`/`fail` handled in
   the loop). Each `agent` node runs as a **fresh** harness context (node N does not inherit node
   N−1's conversation).
3. **Merge** the node's declared `outputs` into the `WorkflowContext`.
4. **Write** a per-step artifact and **advance** `current_id` to `node.next` (or the branch/flow
   target). A `terminal`/`fail` node ends the loop (exit 0 / 1).

**Resume is in-place and automatic.** Each `(workflow, run-id)` maps to one stable run dir; on
start, an existing checkpoint resumes from the checkpointed node with its saved context. A node
that finished but didn't advance the cursor (killed in the gap) is **fast-forwarded** rather than
re-run, so side effects (git commits) aren't duplicated.

## Resilience (fail-soft)

Because runs go unattended for days, an `agent` node never crashes the run; it escalates a ladder
(`runner/agent.py::run_agent`) before advancing:

1. **Transient retry** — rate limits, timeouts, network blips, empty results retry with backoff.
   Scheduled-reset caps (spending/usage/session/quota) are *waited out* to their reset, then retried.
2. **Compact & continue** — on context-window overflow, `/compact` the node's session and retry the
   *same* prompt, preserving progress.
3. **Reframe** — on persistent invocation/parse failure, re-ask from scratch in a fresh session,
   simplifying each attempt.
4. **Default to next** — when reframing is exhausted, emit each output's declared
   `OutputSpec.default` (null if unset) and advance to `next`, so the run continues. Disable with
   `AGENT_USE_DEFAULT_OUTPUTS=false` to hard-fail instead.

Related: [load_workflow](load-workflow.md) (parsing), [AgentBackend](agent-backend.md) (the harness),
[workflow file format](../workflow-format.md) (the on-disk shape).
