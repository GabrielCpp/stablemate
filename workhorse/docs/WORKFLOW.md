# Migrating a `workflow.yaml` to a Python workflow

The YAML front-end is **deleted**. There is no loader, no node types, no `requires:`
preflight, and no `workflow.yaml` anywhere in this repository. There is no generic
`workhorse` command either: each workflow declares its own `workhorse-<name>` console
script, which carries the workflow object itself, so there is nothing to hand a path to.

A workflow is now a Python package whose **states are methods** on a `Workflow` subclass
and whose **nodes are plain functions** collected into a `Blueprint`. If you are writing a
new workflow, read [AUTHORING.md](AUTHORING.md) instead — it is the reference, and this
file is only the bridge from the old schema to it.

This document exists because a YAML workflow is a real thing someone may still be
holding. It maps every construct in the retired schema to what replaces it, names the
handful that have **no** counterpart, and lists what did not change at all. For *why* the
schema was retired rather than extended, see [Why a workflow is Python and not a config
file](../README.md#why-a-workflow-is-python-and-not-a-config-file) — this page assumes
that decision and only translates across it.

---

## What did not change

Port the graph, not the surroundings. These are the same engine underneath and need no
attention during a migration:

- **Prompt templates.** Still Jinja2 `.md` files resolved relative to the workflow
  package, still rendered with a resilient undefined (a missing variable renders empty and
  logs a warning rather than raising), and `node_timeout_s` / `node_timeout_min` are still
  injected so a prompt can size its own work (both read `"unbounded"` when the turn has no
  budget). One thing *did* change: `args:` was a dict of Jinja template **strings**, so it
  stringified an `int` or a `Path` on the way past. `self.agent(args={…})` merges real
  Python objects into the render context instead — a template that worked around the
  stringification (`{{ count | int }}`) no longer needs to.
- **Power tiers.** `power: high` was and is an abstract tier resolved through
  `~/.config/stablemate/config.toml` at `power.<tier>.<backend>` into a concrete
  model/effort. See [BACKENDS.md](BACKENDS.md).
- **The resilience ladder and its knobs.** Transient retries, cap waits, compact-and-
  continue, reframing, and defaulting a turn's outputs all sit *under* the agent turn,
  which both engines drive identically. Every `AGENT_*` variable in
  [GUARDRAILS.md](GUARDRAILS.md) still means what it meant.
- **Run artifacts and auto-resume.** Still `run.json`, `checkpoint.json`, `context.json`
  and per-step folders holding `prompt.md` / `output.json` / `context_after.json`; still
  one stable run dir per `(workflow, run-id)` that resumes if it already holds a
  checkpoint.
- **`--dry-run` and `dot`.** Both survive as subcommands; `--dry-run` now also checks that
  every state name binds and no state is unreachable.

---

## Construct by construct

### Top-level keys

| YAML | Python |
|---|---|
| `name:` | `Registry("acme")`, plus the `[project.scripts]` row that binds it to the `workhorse-acme` command |
| `start:` | the entry class passed to `Registry.main(...)`; the run begins in its method named `start` |
| `vars:` | class attributes on the `Workflow` — still filled by `--params`, and frozen once `setup()` returns |
| `requires:` | **no counterpart** — see below |
| `env:` | **no counterpart** — a node runs in the driver's own process and reads `os.environ` directly; there is no subprocess to inject into |
| `labels:` | a `labels()` method returning `dict[str, str]`, re-read before every transition. Keys are no longer `wf.`-prefixed |
| `nodes:` | state methods (control flow) plus `@blueprint.node` functions (work) |
| `flows:` | `Registry.add_flows(qa=Qa, dev=Dev, …)`, each value a `Workflow` subclass |

### Node types

| YAML node | Python |
|---|---|
| `type: agent` | `self.agent("prompts/plan.md", returns=Plan, args={…}, power=…, timeout=…)` |
| `type: script` | a `@blueprint.node` function, invoked with `self.call(fn, …)` |
| `type: branch` | ordinary `if` / `elif` in the state body |
| `type: terminal` | `return Done(result)` |
| `type: fail` | `raise WorkflowFailed(reason)` |
| `type: flow` | `self.handoff(Qa, story=…, target_env=…)` |
| `next: <id>` | `return Continue(result, self.next_state, **params)` |

### Values between nodes

| YAML | Python |
|---|---|
| `outputs: [{key: plan_result}]` on an agent node | the fields of the model given to `returns=` |
| `outputs:` on a script node | the node function's **return annotation** — a `BaseModel`, or any JSON-able value |
| `default:` on an OutputSpec | **no counterpart** — see below |
| `{{ plan_result.status }}` in a prompt | pass it: `args={"status": plan.status}` |
| `path: result.status` dot-paths | attribute access on the typed value |
| `get_node_output('prepare_story', 'story_path')` | `self.output(prepare_story).story_path` — a read of the recorded artifact, which **raises** `NodeNotRunError` when the node has not run |
| the ambient context map | the three tiers in [AUTHORING.md](AUTHORING.md#the-three-tiers-of-state-and-no-fourth): inputs, `self.ctx`, state parameters. Nothing else crosses a transition |

### The flow `vars` contract

The `null` = required / `""` = optional / anything-else = default convention was a
hand-rolled signature. It is now an actual signature:

```yaml
vars:
  story_path: null          # required
  target_env: "local"       # optional, defaults to "local"
```

```python
class Qa(Workflow):
    story_path: str          # required — no default
    target_env: str = "local"
```

A missing required input now fails at binding time with the parameter's own name.

### Invocation

```bash
# then
workhorse --workflow ./wf/workflow.yaml --params '{"story":"ACME-1"}'

# now — the workflow's own console script, which carries the workflow object
workhorse-coder run --params '{"story":"ACME-1"}'
workhorse-coder run qa --params '{"story":"ACME-1"}'   # a flow, standalone
```

Every other flag (`--runs-dir`, `--run-id`, `--params-file`, `--cli`, `--resume-run`,
`--resume-latest`, `--no-cache`) is unchanged.

### Checkpoints

A checkpoint used to name a node id; it now names `(state, params)`. Old checkpoints are
**refused by name** rather than misread — they share the runs directory with live runs,
and a node id that happened to match a state name would otherwise resume the wrong thing.
A YAML run interrupted mid-flight cannot be resumed by the Python engine; start it over.

Renaming a state strands runs checkpointed on the old name, so both decorators take
`aliases=[…]`. There was no YAML equivalent — the schema had no rename story at all.

---

## What has no counterpart

Three constructs did not survive, and no Python spelling replaces them. Each is a
deliberate consequence of what the port bought, not an oversight:

1. **`requires:` — the tool preflight.** A workflow was a data file that could be handed
   to an engine with no idea what it needed, so the engine had to check first. A workflow
   is now an installed Python distribution: its dependencies go in `[project.dependencies]`
   and `pip`/`uv` resolves them at install time, before a run exists to fail. Consequently
   a node imports its libraries **at module scope** and carries no "if it isn't importable"
   branch — the condition is settled before the package can be imported at all.

2. **`default:` on an OutputSpec.** You could declare the value a node would emit after
   the resilience ladder gave up (`default: {status: blocked}`). There is nothing left to
   declare it for: an exhausted ladder now **stops the run** at its checkpoint instead of
   emitting anything. A fallback value is a fabricated answer wearing the workflow author's
   signature, and every state downstream would treat it as real. A state therefore needs no
   safe arm for an empty agent reply — it never gets one.

3. **Per-node `activity:` as a declared field.** It is now a flagged log record —
   `logger.info("assessing %s", unit, extra={"activity": True})` — because a state is one
   method that may do several things and the interesting one is whichever it is doing now.
   The rendered message *is* the activity, so it is never written twice.

---

## A minimal port, end to end

```yaml
name: example
start: step
vars:
  subject: "the Fibonacci sequence"
nodes:
  - id: step
    type: agent
    prompt: prompts/step.md
    args: {subject: "{{ subject }}"}
    outputs: [{key: result, default: {status: error}}]
    next: decide
  - id: decide
    type: branch
    path: result.status
    cases: {ok: done}
    default: failed
  - id: done
    type: terminal
  - id: failed
    type: fail
```

becomes

```python
from pydantic import BaseModel
from workhorse.cli import console_script
from workhorse.pyflow import Blueprint, Done, Registry, Workflow, WorkflowFailed


class Result(BaseModel):
    status: str = ""


class Example(Workflow):
    subject: str = "the Fibonacci sequence"

    def start(self):
        result = self.agent("prompts/step.md", returns=Result, args={"subject": self.subject})
        if result.status == "ok":
            return Done(result)
        raise WorkflowFailed(f"step returned {result.status!r}")


workflow = Registry("example").add_blueprints(Blueprint("example"))
main = console_script(workflow.entry_point(Example))
```

That pair is a translation, not a runnable file: `prompts/step.md` is whatever prompt the
YAML workflow already had. For something that does run as written — the same shape, with
the prompt and the console script actually in place — read
[`workflows/src/workhorse_workflows/hello_world/workflow.py`](https://github.com/GabrielCpp/stablemate/blob/main/workflows/src/workhorse_workflows/hello_world/workflow.py)
and check your port against it:

```bash
workhorse-hello-world run --dry-run
```

The package layout around it — `pyproject.toml` console script, prompt directory, node
module — and everything the port needs beyond this table are in
[AUTHORING.md](AUTHORING.md).
