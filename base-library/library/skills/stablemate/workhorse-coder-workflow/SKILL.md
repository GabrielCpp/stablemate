---
name: workhorse-coder-workflow
description: "Architecture and conventions for the epic-coder workhorse workflow — the inputs contract, state topology, self.output threading, ostler path integration, and node authoring rules."
tags: [python, backend, standards]
---

# Coder Workflow — Architecture Reference

Load this skill when reading, modifying, or debugging the `coder` workflow —
`workflows/src/workhorse_workflows/coder/`: `workflow.py` (the epic/story state machine),
its nine registered sub-flows, node functions, schemas, and prompts.

The engine API those files are written against — states, `Continue`/`Done`/`Await`,
`self.call`/`agent`/`handoff`/`output` — is `workhorse/docs/AUTHORING.md`. Node-authoring
rules are the `workhorse-scripting` skill. This skill is the coder workflow's
own architecture, and nothing else.

> **Repo modes (mono-repo vs multi-repo) and the docs root.** Before touching any
> `cwd=`/`add_dirs=` on a `self.agent(...)` call, or any path resolution
> (`resolve_impl_context`, `resolve_review_context`, `paths.py`'s three repo-root
> resolvers), read `paths.py`'s module docstring — it states which resolver each caller
> uses and why they differ. The docs root and the affected-repos list carry fewer
> guarantees than they look like they do; see "`docs_path` Threading" below.

---

## Workflow Inputs

Inputs are **class attributes on `Coder`** with defaults, filled from `--params`. They are
frozen after `setup()`. Everything a node produces at runtime is *not* an input — it is a
state parameter or `self.output(node)`.

| Input | Default | Notes |
|-------|---------|-------|
| `mode` | `"epic"` | `"epic"` = full queue; `"story"` = single story, own branch, own PR |
| `docs_path` | `""` | Docs repo root. Empty → the run's `repo_dir` (the docs sit beside the code) |
| `story` | `""` | Story slug (e.g. `"CASE-1234"`). Required in story mode; ignored in epic mode |
| `epic` | `""` | Optional: override which epic to run, skips the queue pick |
| `operator_mode` | `"auto"` | `"auto"` = the `resolve-operator` agent stands in; `"human"` = escalate to a human. The shipped legacy value `"operator"` remains an alias for `"human"`. Does not reach the CI gate, which is always human |
| `target_env` | `"local"` | `"local"` = localhost QA; `"dev"` = shared DEV environment |
| `qa_stack_manifest` | `"qa-stack.yml"` | The stack manifest `qa` reads to bring services up |

The rework caps are **`ClassVar` constants, not inputs** — `MAX_CI_REWORKS` (3),
`MAX_MERGE_REWORKS` (2), `MAX_ZERO_DIFF_COMMITS` (3), plus each flow's own. They were YAML
`vars` duplicated as literals inside the branch guards; now the guard reads the constant, so
there is one copy and a test asserts a cap by *changing it*. Raising a cap is a code change.

Override any input at launch:
```bash
workhorse-coder run --params '{"mode":"story","story":"CASE-1234"}'
```

### Standalone flow invocation

Eight sub-flows are registered by name on the registry (`Registry("coder").add_flows(...)`),
and any of them is independently launchable. All of them are story-oriented: they resolve
`story_path`/`spec_dir` from the story slug via ostler in their own first state, so only the
minimal params are needed:

```bash
# QA only, against DEV
workhorse-coder run qa --params '{"story":"CASE-1234","target_env":"dev"}'

# Dev (plan + implement) only
workhorse-coder run dev --params '{"story":"CASE-1234"}'
```

`docs_path` and `epic` are optional (empty string = derive from CWD / ostler defaults).
Standalone QA clears both the disposable `qa/` tree and the stale root `qa-evidence.json`,
then regenerates context. `plan-context.json` is not required; source-root resolution
degrades to the standalone repository.

`genesis`, `dream` and `fix` exist as names *because* they are entered directly; the other
five are also reached by `self.handoff(...)` from the main machine.

---

## Cross-state values — three tiers, and which to use

There is no `get_node_output()` and no flat context. A value reaches a later state one of
three ways, and picking the wrong one is the defect this section exists to prevent:

1. **An input** (`self.story`, `self.docs_path`) — supplied at launch, frozen, readable
   anywhere.
2. **`self.ctx`** — whatever `setup()` returned, computed once per run. `Coder.setup()`
   returns `WorkspaceDirs`, so every agent turn that needs `add_dirs` reads
   `self.ctx.workspace_dirs` regardless of how far the run got. (In the YAML this node sat
   on the story path only, so the two main-graph turns taking `add_dirs` rendered it empty
   on any run that reached them before the first story. Resolving it in `setup()` is the
   same call at a strictly earlier point.)
3. **A state parameter** — one hop, on the `Continue`: `Continue(result, self.qa, epic=epic,
   triage=triage)`. Counters live here. It is part of the checkpoint, so a resumed run
   gets it back.

`self.output(node)` is a **read of a recorded artifact**, not a fourth tier: it returns the
node's typed return value from this run's directory and **raises `NodeNotRunError`** if the
node has not run. That raise is the feature — the YAML's bare `{{ spec_dir }}` collapsed to
`""` instead, and silently wrong beats loudly missing exactly never.

**The two epic disjunctions look alike and are not.** The port keeps them apart:

- the story pipeline uses `prepare_story.story_epic or select_story.epic or self.epic` —
  the epic the *story* belongs to, discovered by scanning when story mode got a bare slug;
- `commit_story`, `qa_give_up` and `replan_epic` use `select_epic.epic or self.epic` — the
  epic the *queue* is working, which in story mode is whatever the run was invoked with.

Both are fall-back chains because `self.output()` raises for a node that never ran, and in
story mode neither `select_epic` nor `select_story` ever runs. The queue epic is carried as
a **state parameter** rather than read back through a guarded `self.output`, so a resumed
run does not re-derive it.

---

## State Topology

Twenty-seven states cover what was eighty YAML nodes. **Where a state boundary goes:** a
state ends where the *expensive or irreversible* thing begins — each `handoff` to a
sub-flow, each agent turn, each of the two operator gates. Deterministic nodes fold forward
into whichever state branches on them, which is why `dev`, `review`, `document` and `qa`
are four states rather than one: a kill during QA must not re-run the implementation.

Both modes converge on `prepare`, whose `prepare_story` node is the **single canonical
source** for `story_path`, `spec_dir`, `qa_dir`, `story_slug` and `story_epic`. Never
bypass it and never re-derive those paths.

**[references/state-topology.md](references/state-topology.md)** draws all four topologies —
story mode, epic mode, the backlog drain that is nested as well as standalone, and the
hard-gated documentation and QA control planes with their fail-closed routing, bounded
repair counters and audit classification. Read it when adding or reordering a state, when a
run took a branch you did not expect, or when changing what a gate is allowed to conclude.

---

## Ostler Path Integration

Ostler resolves slugs to canonical paths, and nodes command it **in-process** through the
`Ostler` facade — never `run_tool(["ostler", …])`, because the CLI is a different process
with a different interpreter and pipx isolation makes "the shim is on PATH" and "the module
imports" routinely disagree.

A workflow joins the filename **it** owns — `story.md`, `context.md` — onto a directory
ostler resolved, and never spells a `docs/…` path of its own. Catch the raise where a
fallback is genuinely correct; never catch it to emit a **verdict**, because a gate that
could not read the graph is a failure, not a pass.

**[references/ostler-paths.md](references/ostler-paths.md)** has the `ostler path` subcommand
set, the worked `Ostler`-facade callsite with its fallback, and the graph-free `ostler.path`
helpers that honour `docRoots:` without paying for a graph load. Read it when a node needs a
doc path. Full verb→method reference: the `ostler` skill.

---

## Ambient path threading — `repo_dir`, `docs_path`, `workspace_file`

The three are run **inputs**, listed once as `paths.AMBIENT` and declared as the class's
`injects`; a node that needs one just declares a parameter of the same name. None is ever
read from the environment — prohibited across every workflow and enforced by
`make check-no-env`.

**[references/ambient-paths.md](references/ambient-paths.md)** explains why `paths.py` keeps
**three** repo-root resolvers whose disagreement is behavioral, and which to call. Read it
before resolving a repo or docs root in a node.

---

## Node Conventions

### Return a model, raise to fail
A node returns its schema model from `schemas/`; the engine records it and
`self.output(node)` revives it typed. Nothing is printed to communicate. A hard failure is
`raise WorkflowFailed(reason)` — there are no exit codes, and `raise SystemExit` inside a
node kills the driver.

The ostler QA adapters stay deliberately thin: they preserve `passed|failed|blocked|invalid`
in the returned model for every expected state, even where the underlying library call
signals a problem, because those four are *results* for the state to branch on, not errors.

### Defaults belong in the schema
```python
class StoryPick(BaseModel):
    has_story: str = "no"
    story_path: str = ""
    story_slug: str = ""
```
A field's default is declared once, on the model — not re-typed as a `payload` dict in every
node that returns it. It is also what `--dry-run` blanks to, so a pessimistic default here
makes a dry run take the honest arm.

### What bounds the run
There is no gas tank and no `refuel:`. What stops a runaway is `max_transitions`
(`ClassVar` on the workflow — `Coder` raises it to 4000 because eighty nodes with several
loops is not a default-budget shape) and the run-wide `WORKHORSE_MAX_RUNTIME_S`. Forward
progress is expressed as a *counter parameter* on the transition — `ci_rework`,
`merge_rework` — checked against a `ClassVar` cap. A cap that runs out does not end the run:
it escalates to the operator gate, which is an `Await` and is resumable.

### The operator gate applies decisions; it does not make them
In `operator_mode="auto"` a block first buys a `resolve-operator` turn
(`coder/shared/resolution.py`, `power="smart"`, no wall clock). It has two arms:

* **`answered`** — it found the thing that already settles the question and quoted it: a
  record under `<docs-root>/decisions/` (`shared/paths.py::decisions_dir`), a convention in
  `AGENTS.md` or an installed skill, an acceptance criterion in the story's own spec. It
  writes the answer into the story's `context.md` exactly as a human would and the flow
  continues to the same `read_operator` state. Answering also *writes* a decision record, so
  the next run to hit the question reads the ruling instead of parking on it.
* **anything else** — it `Await`s. An unwritten product or scope call, two sources that
  genuinely conflict, a credential or a spend, any block where the resolver is the interested
  party (QA never narrows its own `covers:`, stamps its own status, or edits its own
  evidence), and plain "I am not sure" all belong to a person.

Every lane caps the *resolver*, not the block: `MAX_PLAN_BLOCKS`, `MAX_REVIEW_BLOCKS`,
`MAX_QA_BLOCKS`, and docs' one consult per flow. The budget is spent on an answer exactly as
on an escalation — otherwise a resolver that keeps applying the same rule to a block the rule
does not clear laps forever and no person is ever reached. Past the cap the gate stops
spending resolver turns and asks a human directly, as many times as it takes. There is still
no cap on blocks, and no arm ends the run.

### Idempotency
A resume re-enters a state from the top, so every node that state already called runs again.
Create-or-checkout the branch, skip the commit with nothing staged, look for the open PR
before opening one.

---

## Flow Contracts

A sub-flow is a `Workflow` subclass in `flows/`, with its own inputs, its own `setup()` and
its own `labels()`. The parent enters it with `self.handoff(Flow, ...)`; a caller enters it
by name with `workhorse-coder run <flow>`. **Only the arguments passed cross the boundary** —
a flow cannot see the parent's `ctx`, parameters or node outputs, which is what makes the
standalone invocation honest.

```python
def qa(self, epic: str = "", triage: int = 0) -> Continue:
    result = self.handoff(
        Qa,
        story=self._story.story_slug,
        docs_path=self.docs_path,
        epic=self._story_epic(epic),
        operator_mode=self.operator_mode,
        target_env=self.target_env,
        qa_stack_manifest=self.qa_stack_manifest,
        triage_scope_count=triage,
    )
```

The input-default convention replaces the YAML's `vars:` three-way rule: a flow input with a
default is optional, an input **without** one is required and a launch that omits it fails
before the first state. Prefer `""` over `None` for a string a flow can derive itself.

---

## Checklist: Adding or Modifying a State or Node

- [ ] The node returns a schema model with an annotated return type; nothing is printed
- [ ] Failure is `raise WorkflowFailed(...)`, and the failing arm cannot reach a publishing state
- [ ] Values a later state needs travel as `Continue(..., name=value)` parameters, or come
      from `self.output(node)` — never re-derived, never a bare guessed default
- [ ] `self.output(node)` calls that can legitimately not have run are wrapped for
      `NodeNotRunError` with a stated fallback, not a blanket `except`
- [ ] The node is idempotent — a resume re-enters its state from the top
- [ ] The docs root comes from `find_docs_root(self.docs_path)` or the right `paths.py` resolver
- [ ] Ostler is called through `Ostler(root)`, never a subprocess; the fallback is a path
      convention, never a verdict
- [ ] A renamed state or node carries `aliases=[...]` so in-flight runs still resume
- [ ] `uv run ruff check .` from the repo root, and the flow's test in `workflows/tests/coder/`
