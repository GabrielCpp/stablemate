---
type: format
slug: workflow-format
title: The workflow file format (workflow.yaml)
---
# Workflow file format

The complete YAML schema of a [workflow](concepts/workflow.md) — the data contract from which
the model is regenerable. Parsed and validated by [load_workflow](concepts/load-workflow.md);
consumed by [workhorse run](workhorse.md#run) (executes it) and [workhorse dot](workhorse.md#dot)
(renders it). Its `vars` are what [run](workhorse.md#run)'s `--params` override. A
[script](#script) node's own script may import [scriptutil](concepts/scriptutil.md) for shared
workspace resolution and `git`/`gh` plumbing.

- file: `**/workflow.yaml`
- code: `workhorse/workhorse/graph/loader.py::load_workflow`

## Fields

Top-level keys of a workflow (and of every entry in [flows](#flows), which is itself a full
workflow).

### name
- type: `string` — required: no — default: the file stem (`workflow.yaml` → its dir name)

Human label; names the run dir and the DOT digraph.

### start
- type: `string` (a node id) — required: **yes**

Entry node id; must be a key in [nodes](#nodes) or load fails.

### vars
- type: `map<string, any>` — required: no — default: `{}`

Initial context. A `var` with a **null** default is a **required parameter** (missing at launch
→ error); an **empty-string** default is optional; any other value is the default. Overridden on
a fresh start by [run](workhorse.md#run)'s `--params`/`--params-file` (ignored on resume).

### env
- type: `map<string, string>` (values Jinja2-rendered from context) — required: no — default: `{}`

Environment variables injected into **every** [script](#script) node's subprocess; a node's own
`env` merges on top (node wins per key).

### nodes
- type: `list<Node>` — required: **yes**

The graph. Authored as a YAML list; keyed by each node's `id` at load. Node kinds below.

### flows
- type: `map<string, Workflow>` — required: no — default: `{}`

Named sub-graphs, each a full workflow (this same schema, recursively). A [flow](#flow) node runs
one; each is also runnable standalone via [`workhorse run <workflow> <flow>`](workhorse.md#run).

## Node types

Every node has `id: string` (**required**) and `type: enum` (**required**, the discriminator).
All `next`/target ids must resolve within the same graph (`terminal`/`fail` take no `next`).

### concept: agent — run an LLM turn

An `agent` node runs one LLM turn against a rendered prompt. `next: string|null`.

#### field: prompt
- type: `path`
- required: yes
- semantics: Jinja2 template

#### field: args
- type: `map<string,string>`
- default: `{}`
- semantics: Jinja2, rendered into the prompt

#### field: outputs
- type: `list<OutputSpec>`
- default: `[]`

#### field: power
- type: `enum{low,medium,high}|null`
- default: null → backend default

#### field: timeout
- type: `float|null`
- default: `3600`
- semantics: seconds; `0`/null → engine default `AGENT_RESULT_TIMEOUT_S`; `infinity`/`inf`/`unbounded`/`never` → no limit

#### field: cwd
- type: `string|null`
- default: process CWD
- semantics: Jinja2

#### field: add_dirs
- type: `list<string>|string`
- default: `[]`
- semantics: Jinja2; extra dirs granted

#### field: next
- type: `string|null`

### script
Run a script, capturing one JSON object from stdout as its outputs. Fields: `script: path`
(**required**); `args: list<string>` (Jinja2, positional; default `[]`); `outputs:
list<OutputSpec>` (default `[]`); `cwd: string|null` (default the workflow dir); `env:
map<string,string>` (Jinja2; merged over workflow `env`; default `{}`); `refuel: string|null` (a
context dot-path — reaching this node refuels the gas tank when that value changed since the last
visit; default null); `next: string|null`. A script can import
[`workhorse.scriptutil`](concepts/scriptutil.md) for workspace resolution, JSON/JSONC loading, and
`git`/`gh` plumbing shared across workflows (available because workhorse is installed editable).

### branch
Route to a node by inspecting context. Fields: `path: string` (**required**, a context dot-path);
`cases: map<string,string>` (value→next equality map; default `{}`); `conditions:
list<{op,value,next}>` where `op ∈ {==,!=,<,>,<=,>=}` and `value: string` (numeric compares;
default `[]`); `default: string|null` (fallback next). Evaluation: `cases` first, then
`conditions` in order, then `default`.

### flow
Call a named sub-graph like a function. Fields: `name: string` (**required**, a key in this
graph's [flows](#flows) — validated to exist); `args: map<string,string>` (Jinja2 against the
**parent** context — the only values that cross into the child, alongside the flow's own `vars`;
default `{}`); `outputs: list<OutputSpec>` (keys lifted from the child's terminal context back to
the parent; default `[]`); `next: string|null`.

### call
Invoke a builtin function. Fields: `fn: string` (**required**); `args: map<string,string>`
(Jinja2; default `{}`); `outputs: list<CallOutputSpec>` (an OutputSpec plus optional `wrap:
string|null`; default `[]`); `refuel: string|null`; `next: string|null`.

### terminal / fail
End the run: `terminal` exits 0, `fail` exits 1. No fields beyond `id`/`type`.

### OutputSpec
An entry in a node's `outputs:`. Fields: `key: string` (**required**, the context key to extract);
`default: any` (emitted for this key when the node exhausts the resilience ladder and defaults to
`next`; default null). `CallOutputSpec` adds `wrap: string|null`.

## Sample (load-valid)

```yaml
name: example
start: step
vars:
  subject: "the Fibonacci sequence"
nodes:
  - id: step
    type: agent
    prompt: prompts/step.md
    args: { subject: "{{ subject }}" }
    outputs:
      - key: result
        default: { status: error }
    next: decide
  - id: decide
    type: branch
    path: result.status
    cases: { ok: done }
    default: failed
  - id: done
    type: terminal
  - id: failed
    type: fail
```
