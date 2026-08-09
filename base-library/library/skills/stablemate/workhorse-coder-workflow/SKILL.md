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

Nine sub-flows are registered by name on the registry (`Registry("coder").add_flows(...)`),
and any of them is independently launchable. The eight story-oriented flows resolve
`story_path`/`spec_dir` from the story slug via ostler in their own first state, so only the
minimal params are needed:

```bash
# QA only, against DEV
workhorse-coder run qa --params '{"story":"CASE-1234","target_env":"dev"}'

# Dev (plan + implement) only
workhorse-coder run dev --params '{"story":"CASE-1234"}'

# An already-reviewed prose plan, split into verified commits
workhorse-coder run implement-plan --params '{"plan_path":"/absolute/path/to/plan.md"}'
```

`docs_path` and `epic` are optional (empty string = derive from CWD / ostler defaults).
Standalone QA clears both the disposable `qa/` tree and the stale root `qa-evidence.json`,
then regenerates context. `plan-context.json` is not required; source-root resolution
degrades to the standalone repository.

`genesis`, `dream`, `fix`, and `implement-plan` exist as names *because* they are entered
directly; the other five are also reached by `self.handoff(...)` from the main machine.
`implement-plan` is the exception to the story-input convention: it snapshots `plan_path`,
validates a typed dependency worklist, and owns scoped verification, commit, and push. Completion
also requires an independent semantic review with no actionable findings. Findings become a second
checkpoint-authoritative review worklist; its scoped fixes must pass the same deterministic Git and
verification gates, then survive a fresh review, before the flow returns `complete`.

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
   zero_diff=zero_diff)`. Counters live here. It is part of the checkpoint, so a resumed run
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

Twenty-seven states cover what was eighty YAML nodes. The factor of three is the `decide_*`
nodes disappearing into the `if` at the end of the state that produced the value they branch
on, and the eight `incr_*`/`reset_*`/`init_*` counter nodes becoming keyword arguments.

**Where a state boundary goes:** a state ends where the *expensive or irreversible* thing
begins — each `handoff` to a sub-flow, each agent turn, each of the two operator gates.
Deterministic nodes fold forward into whichever state branches on them. That is why
`prune_epic` sits inside `open_pr` (a straight line) while `dev`, `review`, `document` and
`qa` are four states rather than one: a kill during QA must not re-run the implementation.

### Story Mode
```
start → prepare → dev → review → document → qa → drain… → finalize
      → commit → commit_pr → done
```
`start` cuts the branch itself in story mode, off the current HEAD, recording the base it
came from — the PR at the far end has to target that base, and re-deriving it from the slug
is how the two drifted once.

### Epic Mode
```
start → select_epic → select_story → prepare → dev → review → document → qa
      → drain → fix_plan → fix_dispatch → fix_implement → fix_check → fix_apply
      → fix_recheck → finalize → commit → select_story        (loop within epic)
                                        ↘ [stories exhausted] open_pr
                                          → merge → merge_operator → select_epic
```
`open_pr` pops the epic off the queue before opening the PR — that order is deliberate.
`merge` returns `Continue | Await`: the CI/merge gate is the one place a human is always
allowed to be the next step.

### `prepare` — the convergence state

Both modes pass through `prepare` before `dev`. Its `prepare_story` node is the **single
canonical source** for `story_path`, `spec_dir`, `qa_dir`, `story_slug` and `story_epic`,
returned as one `StoryPaths` model. Never bypass it and never re-derive those paths.

```python
def prepare(self, slug: str = "", epic: str = "", zero_diff: int = 0) -> Continue:
    story = self.call(prepare_story, self.docs_path, slug or self.story, epic or self.epic)
    return Continue(story, self.dev, epic=epic, zero_diff=zero_diff)
```

### The backlog drain is nested as well as standalone

`flows/fix.py` is the standalone drain. States `drain` through `fix_recheck` are the same
seven steps run *inside* a story's run, right after that story goes green. They are not a
`handoff` to `Fix` because the two differ at the far end: the standalone flow documents and
commits each drained item on its own, while the nested copy leaves both to the story's own
`finalize` and `commit`, so one commit covers the story and everything drained behind it.
The duplication is inherited from the YAML and is preserved deliberately.

### Documentation gate topology

The reviewed implementation enters a standalone, hard-gated `docs` flow before QA:

```text
prepare_story -> resolve_documentation_context -> detect_documentation_okf
-> document_story -> build/validate diff-to-OKF context -> verify_story_documentation
-> review_story_documentation -> documentation_done
```

Repositories without an OKF `docs/features/` tree are explicitly not applicable. Once that tree
exists, an unreadable graph, `ostler doctor` error, surface-only production ownership, blocked
authoring, semantic rejection, or exhausted repair budget ends at `documentation_failed`; it may
not proceed to QA or commit. The parent invokes the same flow again after QA/regression/fix-drain
mutations immediately before commit, and before QA-give-up or standalone fix-story commits.
Local monorepos receive deterministic repository-wide code mapping with document roots excluded;
multi-repo/non-Git docs roots
use scoped doctor findings plus the independent semantic reviewer rather than an invalid cross-repo
diff. CI/merge remediation is contract-preserving and must escalate if behavior would change. Run
the phase independently with `workhorse-coder run docs`.

### QA control-plane topology

The primary QA path is fixed:

```text
prepare_story -> clear_qa_evidence -> resolve_qa_context -> detect_qa_okf
-> build_qa_okf_context -> validate_qa_okf_context -> plan_qa
-> validate_qa_plan -> review_qa_plan -> run_qa_plan -> assess_qa_run
-> verify_qa_evidence -> audit_qa -> regression/completion gates
```

`qa-plan.yml` is mandatory for command, browser, and mobile surfaces. Node functions call
`okf.qa_context(...)`, `okf.qa_context_validate(...)`, `okf.qa_validate(...)` and
`okf.qa_run(...)` on the `Ostler` facade (through the `qa_cli` helpers); no QA agent
drives Playwright/Maestro/commands or authors the run log, manifest, or evidence.
`review_qa_plan` independently checks whether the valid plan can reach and observe its
objectives. `assess_qa_run` constructively judges whether each completed run actually did
so and may request bounded plan repair/extension. `audit_qa` sees only an
objective-confirmed, evidence-valid candidate pass, treats plan/evidence as frozen, and
may only let it stand or refute it.

Routing is fail-closed: `invalid` returns to context/planning repair, `blocked` enters
setup/operator handling, `failed` enters defect triage, and only `passed` reaches the
evidence gate and auditor. Never declare a default output of `passed`.

Audit refutations are classified: plan/evidence defects return to planning, while a
product contradiction becomes the normal failed `qa_result` and enters defect triage.
Context grounding, semantic-plan convergence, and product repair use separate bounded
counters. Regression fixes retain one cumulative budget; a pending marker forces fresh
primary QA after a green fix without resetting that budget.

The reviewed implementation's `code:`/`verify:` grounding is hard-gated by the docs flow before
entering QA so impact generation sees current references. Product fixes loop back through
context generation; setup-only fixes may rerun the already validated plan.

---

## Ostler Path Integration

Ostler resolves slugs to canonical paths. Scripts call it instead of hardcoding path patterns.

### CLI Subcommands
```bash
ostler path epic <epic>              # → docs/epics/<NNNN-epic>
ostler path spec <slug>              # → docs/specs/<slug>
ostler path story <epic> <slug>      # → docs/epics/<NNNN-epic>/stories/<slug>/story.md
ostler path branch <slug>            # → <slug>  (bare id — already unique)
ostler path branch <slug> --epic     # → feat/<slug>  (the epic's number is dropped)
```

Epic directories carry their creation order (`0001-checkout-flow`), which is exactly why nothing
here joins `docs/epics/<epic>` by hand — the commands above take the bare slug and return the
folder that exists.

All commands respect `docRoots` from `ostler.yml` / `agents.yml`. Pass `-C <docs_root>` when not running from the docs repo CWD.

### In nodes (Python) — the library facade, never the CLI

Nodes command ostler **in-process** through `Ostler`. There is no `run_tool(["ostler", …])`
here: the CLI is a different process with a different interpreter, and pipx isolation makes
"the shim is on PATH" and "the module imports" routinely disagree.

```python
from ostler import Ostler, path as okf_path

okf = Ostler(docs_root)                        # root discovered upward, like `ostler -C DIR`
spec_dir_rel = okf.spec_path(slug)             # docs/specs/<slug>
try:
    story_path_rel = okf.story_path(epic, slug)
except (OSError, ValueError, RuntimeError):    # an unloadable graph raises; [] means empty
    story_path_rel = ""
# The fallback is the last resort only, for a docs tree ostler could not read at all; it is
# still ostler's layout rule being applied, just without a graph.
story_path = (
    (docs_root / story_path_rel).resolve() if story_path_rel
    else okf_path.story_dir_in(docs_root, epic, slug) / "story.md"
)
```

Note what the fallback is *not*: a `f"docs/epics/{epic}/stories/{slug}/story.md"` literal.
A workflow joins the filename **it** owns — `story.md`, `context.md`, `<gate>-context.md` —
onto a directory ostler resolved, and never spells a `docs/…` path of its own. The graph-free
`ostler.path` helpers (`story_dir_in`, `epic_dir_in`, `epics_index_in`, `backlog_path_in`,
`features_root_in`) exist for exactly this: they honour `docRoots:` and find the numbered
epic folder from a bare slug without paying for a graph load. Full rule and its reasoning:
"A workflow does not spell a doc path" in `workflows/README.md`.

Catch the raise where a fallback is genuinely correct — a path convention the graph cannot
confirm. Never catch it to emit a **verdict**: a gate that could not read the graph is a
failure, not a pass. Full verb→method reference: the `ostler` skill.

---

## Ambient path threading — `repo_dir`, `docs_path`, `workspace_file`

The three are run **inputs**, listed once as `paths.AMBIENT` and declared as the class's
`injects`. A node that needs one just declares a parameter of the same name; `self.call`
and `self.handoff` fill it from the workflow, so the ordinary callsite says nothing. A
callsite value always wins, and an empty field injects nothing, so the target's own default
stands. None of them is ever read from the environment — that is prohibited across every
workflow (`workflows/README.md`, and the `workhorse-scripting` skill) and
enforced by `make check-no-env`; the CLI translates `$FOO` into `--params` at the process
boundary instead.

`paths.py` keeps **three** repo-root resolvers on purpose, because the YAML's scripts did not
agree and the disagreement is behavioral: a run launched from a subdirectory, or from a repo
whose `docs/epics/` exists but whose `.git` does not, lands on a different root under each.
Each takes `repo_dir` first and only falls back to a `cwd` walk when it is empty. Call the
one the node's semantics need:

| Resolver | Marker when `repo_dir` is empty | Used by |
|---|---|---|
| `scriptutil.find_repo_root(repo_dir)` | `agents.yml`/`.git` upward from `cwd` | the consuming code repo |
| `paths.epics_repo_root(repo_dir)` | `agents.yml` or a `docs/epics/` **directory** | `prune_epic` — a docs checkout with no `.git` still gets its queue popped |
| `paths.launch_repo_root(repo_dir)` | `cwd` if project-shaped, else upward | the operator gates — its `cwd`-first probe is what lets a test point a gate at a sandbox by chdir alone |

Docs specifically: `find_docs_root(docs_path, repo_dir)` from `workhorse.scriptutil` — the
explicit path when given, else the repo root, i.e. docs beside the code.

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
progress is expressed as a *counter parameter* on the transition — `zero_diff`, `ci_rework`,
`merge_rework` — checked against a `ClassVar` cap.

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
def qa(self, epic: str = "", zero_diff: int = 0, triage: int = 0) -> Continue:
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
