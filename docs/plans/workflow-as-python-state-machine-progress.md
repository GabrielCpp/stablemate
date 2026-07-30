---
type: ledger
slug: workflow-as-python-state-machine-progress
title: Workflows as Python — execution ledger
status: active
---
# Workflows as Python — execution ledger

Companion to [workflow-as-python-state-machine.md](workflow-as-python-state-machine.md). The plan
is the spec and does not change as work lands; **this file is the state**, and it exists so an
iteration can learn where it is by reading one page instead of re-deriving it from a 1,350-line
design doc, 2,350 lines of driver, and a full test run. That rediscovery is what drove loop 1's
first run into repeated autocompaction.

## How to keep it

Update this file **in the same commit** as the work it describes — not afterwards, not at the end
of the loop. An iteration that ends with the ledger stale has left the next one nothing to read.

Three things earn a line, and nothing else does:

- **What landed**, with its commit, in one sentence.
- **What is next**, specifically enough to start on without re-reading the plan.
- **Decisions re-confirmed** — every time an iteration has to go back to the plan to settle
  something it thought was open. These are the entries that pay for the file: loop 1 lost
  "typed payload models were removed" across a compaction and rebuilt 224 lines of them.

Do not restate the design here, do not paste diffs, and do not keep a narrative of the run. If an
entry is longer than a few lines it belongs in the plan or in the commit message.

## Current position

**Loop 1 is done.** All seven steps are committed. `research` runs end-to-end on the driver
and the YAML engine is still green (`make test && make check-public`).

**Next is loop 1.1**, not loop 2. The porting work was pulled out of loop 2 into its own loop so
that every port lands beside the YAML engine and nothing is deleted until all four workflows run
on the driver — see "Loop 1.1 — port every workflow, decommission nothing" in the plan. Loop 2 is
now deletion only, and its entry gate is this ledger carrying parity evidence per workflow.

Loop 1.1 is **three ports in, one to go**. `research`, `author` and `okf-builder` run on the
driver; `coder` is still YAML. `author` was taken first because it was the first to exercise
`Await` and `handoff`, and it paid: the driver needed four additions (step 1) and the port found
six things the new shape does not reproduce (see "Findings for loop 2"). `okf-builder` then did
what it was there to do — it needed **no driver change at all**, which is the evidence that the
API `author` settled is the API.

Next is **`coder`**, where `self.output(node)` and the three-tier state rule meet 4,366 lines,
71 scripts, 19 awaits and 8 sub-flows. It is too large for one green step, so it lands in **four
stages**, each green and committed on its own: **A** the package foundation plus the three small
sub-flows (`genesis`, `dream`, `fix_ci`) — done; **B** `dev`, `review`, `docs` — done; **C** `qa`
(91 nodes), which inherits `nodes/okf.py` and `ostler_qa.py` from B2 and is itself in three —
**C1** the node layer (done), **C2** the evidence and regression gates (done), **C3** the graph
and its tests (done); **D** the 80-node main graph, `fix`, both pyproject lines, the top-level tests and the
parity record. Only after D does `coder` resolve through an entry point, so loop 1.1's exit gate
is D, not A.

## What landed

| Step | Commit | What |
|---|---|---|
| 1 | `740a6ef` | Workflow discovery via `workhorse.workflows` entry points, not just library paths |
| 3 | `7cae8d1` | farrier stops reading workflow prompts |
| 4 | `5bb7e29` | Unresolvable skill/prompt references are named rather than rendered into a live prompt |
| 5 | `ea47ff7` | The Python state-machine driver — `workhorse/workhorse/pyflow/`, 2,350 lines |
| 6 | `53dc4ba` | State graph read off the source, for `--dry-run` and `dot` |
| — | `5d3f89d` | `research/models.py` → `schemas.py`; `self.agent(power=, timeout=)` reaches the turn |
| 2 | `772b5d0` | The scriptutil split — `workhorse_workflows.kit.{git,github,workspace}`; scriptutil 1000 → 154 lines |
| 7 | `2ea582a` | The `research` port — 30 YAML nodes → 12 states, both pyproject tables, 8 end-to-end tests |
| — | `2637034` | `--dry-run` reports a fail terminal instead of failing on it (the open question below, answered) |

### Loop 1.1

| Step | Commit | What |
|---|---|---|
| 0 | `f4788a3` | `research` restructured into the normative package layout — `nodes/` (3 subject modules + the shared `Blueprint`), tests to `workflows/tests/research/test_workflow.py`. No behavior change; 12 tests still pass |
| 1 | `950a672` | The driver additions `author` asked for, all additive: `self.agent(cwd=, add_dirs=)`, declared dry-run stand-ins (`@node(stub=)`, `Registry.stub_agents`), activity as a flagged log record, JSON-safe checkpoint params. `research` adopts them |
| 2 | `c96f845` | The `author` port — 101 YAML nodes → 26 states + two sub-flows (14 and 6), 48 scripts → `nodes/` by subject + `nodes/survey/`, both pyproject tables, 155 tests |
| 3 | `6049493` | The `okf-builder` port — 29 YAML nodes → 12 states + one sub-flow (19 → 6), 11 scripts → `nodes/` by subject, both pyproject tables, 8 end-to-end tests. No driver change |
| 4 | `87bd040` | `coder` **stage A of four** — the package foundation (`paths.py`, `contract.py`, the shared `Blueprint`, `schemas/`) and the three small sub-flows: `genesis` (18 YAML nodes → 8 states), `dream` (4 → 3), `fix_ci` (11 → 4). 28 end-to-end tests. No driver change |
| 5 | `a62e3fb` | `coder` **stage B1** — the `dev` sub-flow (35 YAML nodes → 13 states) and the story spine (`nodes/story.py`) it shares with the main graph. 16 end-to-end tests. No driver change |
| 6 | `0d8c7e0` | `coder` **stage B2** — the `review` sub-flow (22 YAML nodes → 9 states) and `docs` (23 → 4), plus `nodes/okf.py` and `ostler_qa.py`, both shared with `qa` in stage C. 25 end-to-end tests. No driver change |
| 7 | `572a231` | `coder` **stage C1** — the `qa` sub-flow's node layer: `schemas/qa.py` and `nodes/{qa,backlog,hygiene}.py`, 7 nodes ported from 6 scripts. Parity checked differentially against the scripts themselves. No driver change |
| 8 | `d4ab851` | `coder` **stage C2** — the QA evidence gate and the regression pair: `nodes/{evidence,regression}.py` and 3 models, 3 nodes from 933 script lines. 31 differential comparisons, all identical first run. No driver change |
| 9 | `a7ec0da` | `coder` **stage C3** — the `qa` graph: 91 YAML nodes → 25 states around one `QaLoop` carrier, plus the 17 prompts B2 and C3 reference. 26 end-to-end tests. No driver change |

### Parity — `author`

What was demonstrated, so loop 2 can see exactly how far it goes:

- **Every mode reaches its terminal.** `epic`, `story`, `survey` and `parity-survey` dry-run green,
  as do both sub-flows on their own entry points — each behind the static preflight, which checks
  the untaken branches and every prompt path too.
- **Same artifacts.** The 12 end-to-end tests drive the real nodes against a temp git repo with
  only the agent turn scripted, and assert the artifacts themselves: the ostler graph (epic, seeds,
  stories, `covers`), the commit and its message, story mode's *absence* of a commit, the operator
  context file, and the run labels.
- **Same resume behavior.** A run killed mid-story resumes on that story alone
  (`test_a_run_killed_mid_story_resumes_on_that_story_alone`) — the checkpoint is the state
  parameter, so the loop does not restart from the epic.
- **Not demonstrated:** a side-by-side run of the YAML `author` on the same input. It needs 30+
  real agent turns to reach a terminal, so the comparison is against the YAML's *scripts and node
  wiring*, node by node, not against a recorded run. Where the port could not match the YAML, it is
  a finding below rather than a silent difference.

### Parity — `okf-builder`

- **Every node has a home, and the mapping was checked one by one.** 29 main-graph nodes → 12
  states, 19 walk nodes → 6 states plus one private helper. The collapses are all the same three
  kinds: a `decide_*` router folds into the `if` at the end of the state that produced the value
  it routes on (`decide_start`, `decide_item`, `decide_checkpoint`, `decide_coverage`,
  `decide_auto_waive`, `decide_boot`, `decide_browser`, `decide_wt_*`); a `guard_*` folds into the
  same place (`guard_budget`, `guard_fixup_progress`, `guard_rounds`, `guard_wt_*`); and the four
  `type: fail` terminals (`cannot_build`, `rounds_exhausted`, `budget_exhausted`, `doctor_stuck`)
  become `raise WorkflowFailed` at the site that decides them, which is why the count drops
  without any behavior going with it.
- **Same artifacts.** 8 end-to-end tests drive the real nodes — real `ostler doctor`, real
  coverage join, real git — against a temp repo whose source and book actually correspond, with
  only the agent turn scripted. They assert the artifacts: the worklist items and their states,
  `coverage.json`'s totals, the source inventory's unit codes, the queued repair's `kind`/`target`
  /`context`, and the activity labels.
- **Same convergence and the same refusals.** A complete book drains in one investigation, skips
  the recheck and skips the walk; an investigation's `discovered` opens the items it reveals; a
  dirty doctor queues one `fixup` per file and re-converges; a repair that never lands stops at
  `MAX_STALL_ROUNDS` rather than looping; the item ceiling is a **failure**, not a finished book;
  a non-directory source root fails before the first agent turn.
- **Same resume behavior.** A run killed mid-investigation resumes on that item alone — the
  checkpoint carries `item_target`, the worklist entry is still `active`, and the second drive
  makes exactly one more agent call.
- **Both graphs dry-run green**, the parent and `walkthrough-web` on its own entry point.
- **Not demonstrated:** a recorded side-by-side run of the YAML. Its `--dry-run` is a *static graph
  check*, not an execution trace — it prints `29 nodes: prepare, check_ostler, decide_start, …` and
  stops — so, as with `author`, the comparison is node-by-node against the YAML's wiring and
  scripts. The one thing the port genuinely loses is in the findings below, not absorbed here.

### Parity — `coder`, stage A

Partial by construction: the three sub-flows below are drivable on their own, but `coder` does not
resolve through an entry point until stage D, so the workflow-level parity record is still owed.

- **Same artifacts, asserted rather than inferred.** 28 end-to-end tests drive the real nodes —
  real `git init`/`git commit`, real `agents.yml` merge, real event-log digest, real
  `push_epic_branch` — against temp repos, with only the agent turn and the two out-of-process
  boundaries scripted (`farrier` for `genesis`, the four GitHub exits for `fix_ci`). They assert
  the files: the rendered `agents.yml` with its comments intact after the ruamel round-trip, the
  seeded scaffolds, the dream ledger's JSON and markdown, the deleted inbox.
- **Same skip-ahead behavior.** A branch that did not run leaves no `run_dir/<node>/output.json`,
  which is what the tests read — an existing repo skips `git_init`, an existing service skips the
  skeleton and never re-runs the init command, a failed farrier install never reaches the
  conventions turn.
- **Same resume behavior, per flow.** `genesis` killed in the repair turn resumes on `fix` with
  `reworks` intact and re-runs neither the build nor farrier; `dream` killed in the reflection
  resumes on `reflect`; `fix_ci` killed in the fixer resumes on `fix` with the picked repo, the
  processed list, the attempt count and the poll's summary on the checkpoint, and does not re-poll.
- **Not demonstrated yet:** the sub-flows under `handoff` from the main graph (stage D), and — as
  with the other ports — a recorded side-by-side run of the YAML, for the reason in the findings.

### Parity — `coder`, stage B1 (`dev`)

`dev` is the flow with the most gates of any sub-graph in the tree — four of them, three bounded
and one that escalates to a human — so the record here is mostly about the gates.

- **Every node has a home, checked one by one.** 35 YAML nodes → 13 states. The collapses are the
  same three kinds every port has used: the four `decide_*` routers (`decide_plan`,
  `decide_reuse`, `decide_validation`, `decide_lint_layer`, `decide_impl_layer`,
  `decide_operator_scope`) fold into the `if` at the end of the state that produced the value; the
  three `guard_*` nodes (`guard_reuse`, `guard_validate`, `guard_lint`) fold into the same place;
  and the six counter nodes (`reset_plan`, `seed_reuse`, `incr_reuse`, `incr_plan_rework`,
  `reset_lint`, `incr_lint`) disappear entirely, because a counter is a state parameter now.
- **Same artifacts, and no seam past the agent turn.** The 16 end-to-end tests run a real authored
  story in a real docs git repo, two real code repos named by a real `.code-workspace`, real
  `stamp_specs`, real `branch_code_repos` and a real `run_lint` that shells out. They assert the
  artifacts: the front-matter `type:` that stamping adds to each untyped plan file, the branch each
  code repo actually moved onto, the operator context file's `STATUS: ANSWERED` → `CONSUMED` flip,
  and the per-layer implement calls in `implementation_order`.
- **Same gate arithmetic.** Each bounded gate is pinned twice — once taking the repair arm and once
  exhausting it: the reuse gate reworks and re-checks, then proceeds *anyway* at
  `max_reuse_reworks`; the path gate refines four times and only then reaches the operator
  (`MAX_VALIDATE_REWORKS`); the lint gate fixes and re-runs until clean, and moves on dirty at
  `max_lint_reworks`. The permissive defaults are pinned too — a blank `status` takes `done`/`ok`
  /`valid`, which is the YAML's `default:` arm.
- **Same operator behavior in both modes.** `auto` runs the resolver turn and reworks on
  `answered`; an `escalated` resolver falls through to the human wait; `human` waits on the story's
  `context.md` directly; an `epic`-scoped answer leaves the flow with `status="replan"` instead of
  retrying; and a context file that never says `ANSWERED` is not treated as an answer.
- **Same resume behavior.** A run killed inside `implement-plan` resumes on `implement` with
  `index=0` on the checkpoint — the layer loop restarts on the layer that died, not at planning.
- **The reserved-name trap bit again, and is pinned by a test.** `dev`'s path gate is
  `validate_paths`, not `validate`; `test_validate_is_not_a_reserved_pydantic_name` asserts both
  that `validate_paths` is a state and that `validate` is not, so the rename cannot quietly regress.
- **Not demonstrated:** `dev` under `handoff` from the main graph (stage D), and — as with every
  port in this loop — a recorded side-by-side YAML run.

### Parity — `coder`, stage B2 (`review`, `docs`)

**The lead here is a defect the port itself introduced and the tests caught**, because the work
order's rule is that a behavior you cannot reproduce is a finding, not a difference to absorb.
`build_okf_context` ported `build-qa-okf-context.py`'s "blank `docs_path` → let `Ostler` discover
its own root" literally. Under the YAML that was correct: the node carried `cwd: docs_repo_path`,
so discovery landed on the docs repo. A driver node has no per-node cwd, so discovery landed on
the *orchestrating* repo instead and the packet was diffed against the wrong git tree —
`'…/acme/docs/features' is outside repository at '…/stablemate'`, thrown by the docs flow's
local-mode test. The fix resolves through `find_docs_root(docs_path)`, which is what the sibling
validator node already did and what the YAML's `cwd:` really meant; the local path then converges
in one pass with build, validate and gate all `passed`. This is the class of bug the package's
"the repo a node works on is a parameter, never the process's cwd" rule exists to prevent, and it
is the first time in this loop that the rule caught something rather than merely being followed.
Every other cwd-sensitive node is worth the same read in C and D.

- **Every node has a home, checked one by one.** `review` 22 YAML nodes → 9 states, `docs` 23 → 4.
  Same three collapses as every port before it: the eight routers (`decide_impl`,
  `decide_apply_review`, `decide_impl_feedback`, `decide_documentation_story`,
  `decide_documentation_okf`, `decide_documentation_result`,
  `decide_documentation_context_mode`, `decide_documentation_gate`, `decide_documentation_review`)
  fold into the `if` at the end of the state that produced the value; the guards (`guard_review`,
  `gate_review`, `guard_documentation`) fold into the same place; and the counter `call` nodes
  (`reset_review`, `incr_review`, `reset_documentation_rework`, `incr_documentation_rework`)
  disappear, because a counter is a state parameter now. `docs` collapses hardest — 23 → 4 —
  because its `mark_*` nodes are `Done(...)` terminals, its `fail` node is a `raise
  WorkflowFailed` at the deciding site, and its packet chain is two calls into `nodes/okf.py`.
- **No seam past the agent turn, in either flow.** `review`'s 14 tests run a real
  `resolve_review_context` against a real `plan-context.json` and `.code-workspace`, real
  `stamp_specs`, and a **real `Ostler.settle_review`** behind `verify_review_resolution`.
  `docs`'s 11 run real `detect_okf_docs`, real `classify_documentation_context`, and — in local
  mode — a real ostler QA-context build, validate and gate over a real diff.
- **The anti-gaming gate is demonstrated end to end, which is the strongest evidence in B2.** The
  apply turn claims `applied` while citing an `evidence.md` that is not on disk; ostler's
  settlement ledger opens the finding and the gate downgrades to `needs_changes`; the second pass
  writes the artifact and the identical claim is allowed through. The observable artifacts are
  `review-settlement.json` (`all_verified: true`, `verified: ["F1"]`) and the story's
  `Review fixes applied` status line. A prompt mandate could not have produced that; the gate did.
- **Same routing in every documentation mode.** No OKF book → `not_applicable` with **zero agent
  calls**; a code repo outside the docs worktree → `semantic`, no packet built; a repo alongside
  the docs → `local`, packet built *and* validated *and* gated, with `source_roots == ["acme=."]`.
  A `documented` claim naming no nodes is sent back by the gate and never reaches the reviewer.
- **Same budget arithmetic, and the same two things that happen at the ceiling.** Each bounded
  loop is pinned twice, taking the repair arm and exhausting it: `review`'s apply loop re-applies
  and then **reaches the operator** at the ceiling (it escalates rather than proceeding, which is
  the YAML's `gate_review` arm), while `docs` reworks and then fails with
  `"did not converge in 4 passes"`. A `blocked` settlement escalates to the operator *without*
  spending a rework pass; a `blocked` documentation review raises `WorkflowFailed` at the deciding
  site instead of routing to `documentation_failed`.
- **Same operator and feedback behavior.** `human` mode waits on the story's `context.md`
  directly; an `escalated` resolver falls through to the same wait; an `answered` resolution never
  waits at all — the operator-gate split this loop settled, once more without a driver change. One
  dropped note in the feedback inbox buys exactly one rework pass, because reading it stamps
  `CONSUMED`.
- **Same resume behavior, twice.** A run killed inside `code-review` resumes on `review` with the
  two bound models on the checkpoint; a run killed inside `review-story-documentation` resumes on
  `Docs.review` with `author.nodes == ["docs/features/widget.md"]`. Both confirm the rule the
  driver already stated: **only the kwargs a transition actually binds land in `resume.params`** —
  `review_rework` keeps its default on the way back in, which is the same `0` the killed run was
  carrying, so the omission is not a loss.
- **Not demonstrated:** either flow under `handoff` from the main graph (stage D); the
  `review`/`docs` interaction with `qa`'s copy of the OKF packet (stage C); and, as everywhere in
  this loop, a recorded side-by-side YAML run.

### Parity — `coder`, stage C1 (the `qa` node layer)

Stage C is the size test, so it lands in three: **C1** the node layer (here), **C2** the evidence
and regression gates, **C3** the 91-node graph itself plus its end-to-end tests. C1 has no flow to
drive yet, so its parity claim is made a different way — and, for the first time in this loop,
against a **recorded run of the original**, not against a node-by-node reading of it.

- **Differential parity, not asserted parity.** Six of the seven nodes come from standalone
  scripts that need no agent turn, so the port was checked by running the YAML script and the
  ported node against the *same* throwaway git repo and comparing what each produced.
  `check-sentinel-ids` (dirty branch and clean), `flush-root-screenshots` and
  `append-backlog-item` each agree with their script on **every** field they emit — status, the
  full `notes` prose, the counts — and `append-backlog-item` additionally produces a
  `docs/backlog.md` **identical byte for byte** to the script's, including where each item landed
  under which heading. That is the side-by-side comparison the earlier stages could not get,
  because these nodes are the part of `coder` with no agent in the loop.
- **The three de-dup signals survive the port intact.** The differential run plants an id
  collision after kebab-casing (`"Fix Login"` vs `fix-login`) and a description collision under a
  different id, and both engines skip both and file the other two — 2 appended, 2 skipped, same
  note string, same file on disk.
- **`clear-qa-gate-state.py` deliberately has no node**, and this is the clearest instance yet of
  the shape doing the work. Its whole body zeroed five keys the QA loop carried between passes.
  Under the driver those five are the flow's own state parameters, so "forget them" is simply the
  transition out of `plan_qa` not carrying them forward. Nothing was narrowed; the script's job
  moved into the transition, where it is checkable.
- **The size test's answer, decided here.** At 91 nodes the `qa` graph's shared mutable state is 5
  counters, 3 flags, `qa_failure_class`, `triage_scope_count`, the running `qa_result` and four
  gate-diagnostic note strings. One-parameter-per-var would put ~12 parameters on ~24 states, so
  C3 threads a single pydantic `QaLoop` carrier as **one** state parameter. This is legal without
  any driver change (models round-trip through checkpoints, settled in `author`) and it hides
  nothing, because every state in this one cycle needs essentially the whole loop state. It is a
  representation choice inside the existing shape — **not** an API change, and `self.output(node)`
  did not break.
- **`QaResult` is one model where the YAML kept one key.** Nine different writers wrote
  `qa_result` in three payload shapes; the port keeps them one model rather than nine, and keeps
  the status vocabularies separate (ostler's four states vs the plan validator's two off a
  returncode) rather than unifying them into a vocabulary neither side used.
- **The two hygiene gates keep disagreeing on purpose.** A screenshot that cannot be moved is
  logged and the flow continues; a sentinel ID fails the pass. Every *failure to run* the sentinel
  gate still returns `passed`, exactly as the script did — it diffs a branch, and a repo with no
  history has no added lines to be wrong about. The gate that fails closed is the evidence gate,
  in C2.
- **No repo parameter for the hygiene nodes, and that is the faithful port.** Neither YAML node
  carried a `cwd:`, so no-arg `find_repo_root()` resolves the same repo it always did. The wider
  problem this touches is already recorded as the per-node-cwd finding below; C1 does not widen it.
- **Not demonstrated:** the `qa` flow itself — no graph exists until C3, so nothing here is driven
  through a transition yet, and the four node modules have no flow test until then. `ensure_stack`
  and `run_qa_plan` shell out to docker and ostler and were **not** exercised in the differential
  run; their parity claim is owed in C3 and is not made here.

### Parity — `coder`, stage C2 (the evidence and regression gates)

Three scripts, 933 lines, and the two gates C1 said it was not making a claim about. Same method
as C1 and a wider one: **31 differential comparisons**, each running the YAML script and the ported
node against the same throwaway git repo and comparing every field. All 31 agreed on the first
run, with no adjustment to either side.

- **The gate that fails closed now has its evidence.** `verify_qa_evidence.py` is 510 lines of
  accumulating checks and the only place in the QA flow where "I could not evaluate this" is
  itself a problem. Thirteen cases were run head to head: the three passthrough statuses, no
  `spec_dir`, a missing evidence file, unparsable JSON, the un-modeled-surface admission (both
  with and without a clean run log), a clean single-criterion pass, one case exercising **all four
  criterion kinds** with every sub-check failing at once (divergent parity row, unverdicted row,
  non-existent row evidence, `persisted:false`, `bled_to_others:true`, a missing transient proof,
  an outright `fail` verdict, an unknown `kind`), the four machine files all missing at once with
  an incoherent `runId`, the OKF-obligation checks, and the `visual_fidelity` reports. Both engines
  produce **the same status and the same multi-line problem list in the same order** every time.
  Order matters here and was the thing most at risk: the note is one joined list, so a helper
  split that reordered the checks would read as a passing port and ship a different gate.
- **The one case that let the real ostler run agreed too.** `Ostler.artifact_vet` is stubbed for
  twelve of the thirteen cases so the comparison is about the gate's logic rather than about
  whether a temp repo has a loadable book. The thirteenth leaves it unstubbed, and both sides emit
  the identical `[ostler] qa-evidence validation could not run (…)` problem — which is the branch
  that matters most, since it is the one that turns an unavailable contract into a rejection
  rather than a silent pass.
- **The evidence gate roots ostler at the repo, and that disagreement was kept.** Every other
  helper in `ostler_qa.py` roots at `find_docs_root(docs_path)`; this one at `find_repo_root()`,
  because the artifact it vets is resolved against the repo. `artifact_vet` therefore takes `root`
  as a keyword instead of inheriting the module's convention. Harmonizing it would have been
  invisible on a single-checkout run and would have vetted nothing on a docs checkout.
- **The regression pair fails open, and stays that way.** `detect-regression-platform.py` returns
  `none` for an unreadable plan-context — the opposite default from every gate around it, and
  correct, because it is a router and a story with no UI must not be blocked by a file it had no
  reason to write. Six cases (services→web/mobile/both/none, the legacy flat `touched_layers`
  fallback with its deliberately narrower map, and a missing plan-context) agree exactly, paths
  and layers included.
- **"Nothing to run" is `passed`, verified on both sides.** `run-regression-suite.py` treats a
  missing `Makefile`, a missing `e2e-journeys` target, an absent or flow-less `maestro_flows/` and
  an unknown platform as skips — a repo with no regression suite has not failed one — while
  keeping `blocked` for the case that looks similar and is not: the plan names a web service and
  no web repo resolves in the workspace. Six cases cover skip, unresolved-repo, the `both` merge
  of one skip against one unresolved, and the two nothing-to-run platforms; all agree, including
  the merged `" | "`-joined notes and the worst-status-wins rule. The real subprocess paths
  (`make e2e-journeys`, `maestro test`) are **not** exercised — see "Not demonstrated".
- **The duplicated `qa_result` key became a method, not a second return.** The script printed its
  verdict twice, once as `regression_run` and once trimmed to status/notes as `qa_result`, so the
  shared `blocked → guard_setup → setup_fix` loop would pick it up. A node returns one model, so
  the mirror is `RegressionRun.as_qa_result()`, called at the flow's transition site in C3. The
  differential run compares **both** outputs — the model against `regression_run`, and
  `as_qa_result()` against the script's `qa_result` — for all six cases, so the mirror is checked
  rather than assumed.
- **One narrowing avoided by reading the exception list.** `detect-regression-platform.py` carried
  a private `_load_json` catching `(FileNotFoundError, json.JSONDecodeError, OSError)` and
  returning `{}`. That is `scriptutil.load_json`'s behavior exactly, so the node uses the engine's
  copy; only the diagnostic's channel changes, which is the established `[script-name]`-prefix
  rule. Had the tuples differed, the private one would have had to stay.
- **Not demonstrated:** the two subprocess arms of the regression runner (a real `make
  e2e-journeys` and a real `maestro test`, including the Playwright failure-line regex and the
  timeout→`blocked` path) — neither tool is available here, and the failure-parsing branches are
  reached only by a genuinely failing suite. The regexes are ported byte-identical and the
  surrounding classification is covered, but the claim stops there. Also still owed from C1 and
  not made here: `ensure_stack` and `run_qa_plan`, which shell out to docker and ostler.

### Parity — `coder`, stage C3 (the `qa` graph)

The largest sub-flow in the tree: **91 YAML nodes → 25 states**. Twenty-nine of the nodes were
branch routers that fold into the `if` at the end of the state that produced the value they read,
eleven were counter/flag mutators that become fields on the carrier, four were `emit-kv` terminals
that become the `Done` value, and six were the setup/gate chain that collapses into two helpers.
The method here is not C1's and C2's node-level differential — those already compared every node
against its script — but **26 end-to-end tests through the real driver**
(`workflows/tests/coder/flows/test_qa.py`), one per branch the graph can take.

- **One carrier, and the driver already supported it.** All eighteen loop-carried values —
  the running `QaResult`, five sets of gate notes, six counters, three flags — travel as a single
  `QaLoop` model bound to one state parameter. C1 predicted this would need no driver change and
  it did not: the resume test kills a run mid-`audit-qa`, reads the checkpoint back, and re-enters
  `audit` with the whole carrier intact (`resume.params["loop"]["qa"]["status"] == "passed"`) —
  without re-running the QA suite to rebuild it. That is the state-granularity rule surviving the
  size test, which is the thing stage C existed to find out.
- **The evidence gate is exercised through the flow, not around it.** The scripted `ostler qa run`
  writes what the real runner writes — `qa-evidence.json`, `qa/qa-run.ndjson`, `qa/run-manifest.json`
  — so `verify_qa_evidence` reads real files off disk and reaches its verdict on its own terms. A
  pass here is one the gate had to be convinced of. The fail-closed direction is covered too: a
  non-empty `artifact_vet` problem list turns a runner pass into `invalid`, which routes to
  **replanning** rather than into the fix loop, and the auditor never sees it.
- **The two claims C1 and C2 deferred are now made.** `ensure_stack` is driven through both arms
  with a real `qa-stack.yml` on disk and docker seamed at `workhorse.stack.ensure_stack` — a stack
  that comes up on the second try after one `setup_fix`, and one that never does. `run_qa_plan`'s
  four statuses are driven through the graph rather than asserted on the node. The real
  `make e2e-journeys` subprocess is still seamed (C2's "not demonstrated" stands for the shell
  command itself), but everything above it — platform detection off a real `.code-workspace`, the
  fix→re-run→re-QA round trip, the three-attempt bound — runs for real.
- **Every loop was made to terminate on purpose, and the bound is asserted.** Context repair caps
  at 3, plan rework at 3 (four plan turns), QA fixes at 3 plus **one bonus pass reserved for an
  `evidence`-class failure** — a `code`-class failure gets three and a test asserts the difference,
  because that asymmetry is easy to port as "four" and is not.
- **`add_dirs` is `affected_repo_paths`, not the workspace, and that is now checkable.** `dev` and
  `docs` grant the whole workspace; every one of `qa`'s eleven agent turns grants only the repos the
  plan touched, exactly as its YAML did. The engine's `AgentNode` reaches the scripted agent, so the
  test reads `node.add_dirs` and asserts it against `resolve_impl_context`'s recorded output — the
  one place in the suite that would notice if a port quietly widened a grant.
- **Seven divergences, all recorded in `flows/qa.py`'s docstring.** The load-bearing ones: the
  two-key `repair-qa-context` reply became a model with both halves rather than two outputs; an
  empty `story_path` ends `exhausted` rather than failing (`docs` raises on the same condition —
  the divergence is the YAML's, and is preserved); the five `max_*` budgets are `ClassVar` because
  the YAML never declared them as flow vars; `clear_qa_gate_state` became `QaLoop.cleared()` on the
  transition out of the plan turn. `decide_qa_run`'s `blocked` arm is unreachable in the YAML and is
  preserved unreachable.
- **Not demonstrated:** the real `make e2e-journeys` / `maestro test` subprocesses (unchanged from
  C2), and `stamp_specs` against a book with a real id ledger — it runs for real here, but on a temp
  repo whose ostler book is empty, so only the no-op and single-spec paths are covered.

## Findings for loop 2

Not deletions — this loop deletes nothing. Each is either something the port could not reproduce
or something it left stranded.

- **`Await` replaces the file, `await-operator.py` appended.** `_ask()` writes the questions with
  `path.write_text()`, so a second block on the same context file overwrites the first block's
  questions *and* the operator's answer to them. The YAML re-armed in place and preserved the prose.
  The resolver prompts now treat their own prior `## Your answers` section as the loop guard, which
  is what survives — but the transcript loss is real, and the fix is in the driver.
- **No `Await` escape under `--dry-run`.** A dry run that reaches an await blocks on a real file
  poll. `author` gets past it because `operator_mode=auto` routes around the awaits;
  `operator_mode=human` cannot dry-run at all.
- **The prompts' `STATUS: CONSUMED` protocol was stale, and is now corrected.** Only
  `await-operator.py` ever wrote `CONSUMED`; under the driver the three resolver prompts were
  naming a marker nothing writes. They now route on the reply's `decision` field and use the file
  as the transcript. The YAML copies in `base-library/` still carry the old text — same defect,
  same fix, deliberately not touched while the YAML engine is live.
- **`handoff()` takes keywords only.** A `Workflow` subclass is a pydantic model, so a sub-flow's
  inputs bind by name; positional args raise. Worth an explicit error rather than the pydantic one.
- **Stranded by this port:** both `await-operator.py` copies (280 lines of ctypes inotify each),
  `init_counter.py`/`incr_counter.py` (the counter is a state parameter now), and the unreferenced
  `board.py`, `checkout-workspace.py`, `gh-token.py`.
- **groom stamps activity labels with a prefix.** The driver's labels are unprefixed by decision;
  groom is the side that changes.
- **`refuel:` has no counterpart, and this is the one thing `okf-builder` loses.** Both of its
  `select_item` nodes carry `refuel: done_count` — the YAML's transition budget is a gas tank that
  *refills on evidence of progress*, so a loop still completing items may run indefinitely while a
  loop that has stopped completing them runs dry and halts. The driver has a flat transition
  budget: it bounds the machine, but it cannot tell a productive long run from a spin. Nothing was
  invented to replace it; both ceilings the port does enforce (`max_items`, `MAX_STALL_ROUNDS`) are
  narrower guards that happen to cover the two loops that spin in practice. Reported, not absorbed
  — a driver-side refuel is a loop-2 design question, not a port decision.
- **The YAML's `--dry-run` is a static graph check, not an execution trace.** It lists the node
  ids and stops, which is why no port in this loop can show a recorded side-by-side run against
  the YAML. The pyflow `--dry-run` *does* execute, through declared stand-ins. Worth noting when
  loop 2 decides what "the YAML engine still works" was ever able to mean.
- **Stranded by this port:** nothing in `okf-builder/scripts/` — all 11 have a home. What goes
  stale instead is `boot-app.py`'s `--teardown` argv sentinel (one script serving as two nodes
  became four nodes and a private `_finish`), and `record.py`'s `ast.literal_eval` tolerance for
  Python-repr `discovered` lists, which is unreachable once the agent reply is a typed model.
- **Every public name on `dir(Workflow)` is reserved, and one collision is silent.** `Workflow` is
  a pydantic model, so an input field that shadows a parent attribute at least *warns*
  (`dream`'s documented `run_dir` var had to become `reflect_on` with `run_dir` kept as an alias),
  but a **state method** that shadows one is simply not a state and nothing says so — `genesis`'s
  `validate` state was silently unregistered until it was renamed `verify`. The trap is the
  pydantic-v1 deprecated aliases nobody thinks of as API: `validate`, `json`, `dict`, `copy`,
  `schema`. Both fixes were workflow-side, so no driver change was made; a `__init_subclass__`
  check that rejects a shadowing state by name is a loop-2 driver question. **It has now bitten
  twice**: `coder`'s `dev` flow wanted a `validate` state for the path gate and it is
  `validate_paths` for the same reason, pinned by
  `test_validate_is_not_a_reserved_pydantic_name`. Two workflows out of four hit the same name;
  that is a rate, not a coincidence.
- **The `fix_ci` attempt budget is a lifetime one, not the per-repo one its comment claims.**
  `ci_attempts` is never reset when `select_ci_repo` advances, so a second repo inherits whatever
  the first spent — a repo that needed one fix leaves the next one two instead of three. Behavior
  preserved and now pinned by a test
  (`test_the_attempt_budget_is_shared_across_repos_not_reset_per_repo`); repairing it is a
  behavior change, so it is reported rather than absorbed.
- **`fix_ci`'s `ci_summary` input is unreachable.** The main graph passes the CI summary in through
  the `type: flow` node, but `poll` always runs before `fix` and overwrites the var, so the fixer
  can never see it. Kept for interface parity, never read, and pinned by the fix test asserting the
  fixer gets the poll's summary instead.
- **`max_genesis_reworks` was an inert var.** The YAML declared it and the repair loop branched on
  a literal `2` instead; the port's `MAX_REWORKS` makes the real ceiling the only ceiling. Same
  number, so no behavior moved — but the var was operator-settable and did nothing.
- **A latent multi-repo defect in the YAML's CI push.** `push-ci.py` ran `push-epic.py`, which
  resolves its repo with `find_repo_root()` and so prefers `AGENT_REPO_DIR`, while every `fix_ci`
  node was pinned to the picked repo with `cwd:`. In a multi-repo workspace with that variable set,
  the loop polled one repo's PR and pushed a different repo's branch. The port takes `repo_dir`
  like its neighbours and falls back to `find_repo_root()` only when handed nothing, which is the
  single-repo case the YAML got right.
- **One narrowing, in `coder/paths.py`, and it is the only one in stage A.** The `await-*` scripts
  resolved the launch checkout through four rungs; the fourth was a walk upward from `__file__`,
  reached only when nothing above it matched. Under the driver `__file__` is the installed
  `workhorse_workflows` package, never the consuming repo, so that rung could only ever have
  returned something wrong. It is dropped rather than ported. Flagged here because this loop
  narrows nothing without saying so.
- **The context manifest never reaches a pyflow prompt, and the degradation is silent. This is
  the largest parity gap in the loop, and it is engine-side, not port-side.** The YAML engine
  loads farrier's per-repo `.agents/agents-context.json` and merges it into *every* render
  context (`main.py`: `WorkflowContext(initial={**manifest, …})`, and a sub-flow's child context
  is `{manifest, flow.vars, rendered_args}`). `pyflow`'s agent turn renders against
  `WorkflowContext(jsonable(args))` and nothing else (`engine.py:316`), and `pyflow/run.py` never
  reads a manifest at all. Five things follow, none of which any port can fix from the workflow
  side:
  - `instruction_ref()` / `prompt_ref()` resolve against an empty map, so each one renders the
    placeholder sentence `generated <name> instruction file when installed` **into a live agent
    prompt**. `author` has 6 prompts doing this, `okf-builder` 4 (via `skill_load_ref`), `coder`
    2 of the 10 ported so far — `refine-plan.md`, which `dev` renders on three of its four
    gates, carries 22 `instruction_ref` calls.
  - `template.*` and `repo.name` render empty. `refine-plan.md` mostly survives on
    `| default(...)` filters, so it silently reverts to the *generic* layer names and paths the
    defaults encode rather than the repo's own — the exact drift the manifest exists to prevent.
    `author`'s three `{{ repo.name | title }}` headings have no default and render as a blank.
  - `get_node_output()` is inert: it reads `_run_dir` off the context, which is absent.
  - `skill_dir()` falls back to the workflow package directory, which is not where any skill is.
  - **And it is silent**, because `_farrier_globals`' `unresolved()` warning is gated on
    `manifest_present`, which is false — the one path designed to report this is the path the gap
    switches off. `workhorse.references`' pre-run static scan is likewise skipped for pyflow.
  Repo-authored flavor overrides (`<repo>/.agents/flavors/<workflow>/<node>.md`) go with it, for
  the same reason: `_repo_root` is a manifest key. The fix is a handful of lines in
  `pyflow/run.py` and `engine.py` — load the manifest the way `main.py` does and merge it under
  the render args — but it is an **engine** change and it touches every port already landed, so
  it is reported here rather than made. Nothing was invented to work around it.
- **`dev`'s three rework budgets were all inert vars, and the port makes two of them live.**
  Every one of the flow's bounded loops branches on a *literal* with a comment saying "keep in
  sync with `vars.max_*`" — `"2"` for reuse, `"3"` for validate, `"2"` for lint — so setting any
  of them on the command line changed nothing. `max_validate_reworks` is worse than inert: it is
  declared in the **top-level** workflow vars (line 152), never in `dev`'s, and a flow's context
  is `{manifest, flow.vars, rendered_args}`, so it could not have reached the flow even if a
  branch had read it. The port keeps `max_lint_reworks` and `max_reuse_reworks` as real inputs
  (same defaults, now actually honoured) and makes the third a `ClassVar` `MAX_VALIDATE_REWORKS
  = 3`, matching the literal that was really in force. Same numbers, so no run changes — but two
  knobs that did nothing now do something, which is a divergence and not a bug fix to absorb
  quietly.
- **`stamp_specs` never re-runs after a refine pass, and the port preserves that.** The YAML
  stamps the plan files' front matter once, right after the first `plan` turn; `rework_plan` goes
  to `decide_plan` and `rework_plan_paths` to `incr_plan_rework`, so neither passes through
  `stamp_specs_plan`. A refine that writes a *new* plan file leaves it untyped for the rest of the
  run. Kept as-is because changing it is a behavior change; worth a decision in loop 2, since
  `stamp_specs` is idempotent and re-running it would cost nothing.
- **`implement-plan.md` reads three values the YAML node never passed it.** The prompt renders
  `story_path`, `spec_dir` and `impl_instruction_paths` from the flow context, which the YAML
  supplied ambiently because context is global there. Under `pyflow` the render context is the
  `args` dict alone, so the port passes all three explicitly from `implement`'s state parameters.
  This is the general shape of the manifest gap in miniature — and the reason it is worth
  saying twice: **a YAML prompt may read anything in context, and only the ones a port notices get
  passed.** A sweep of every ported prompt's free variables against its call site is a loop-2 task.
- **`qa_source_roots_json` was a JSON-encoded string; it is a `list[str]` now.** Same reason
  `fix_ci`'s `processed_repos` was: a workflow var is a string, a state parameter is a value.
  Nothing on disk carried the encoded form.
- **`PlanResult.services` has two live, conflicting shapes and no consumer.** `plan-story.md`
  asks for a list of `"repo::path"` strings and `refine-plan.md` for a list of
  `{repo, path, type}` objects. Nothing in the flow ever reads the field — `plan-context.json`,
  written by the same turn, is what every downstream node decodes — so the port models neither
  and lets `extra="ignore"` drop whichever arrives. Picking a winner is a prompt decision, not a
  port decision.
- **`resolve_ci_workspace` and `resolve_workspace_dirs` were the same script twice.** They are one
  node now, with `resolve_ci_workspace` kept as a `@blueprint.node(aliases=…)` so a run
  checkpointed on the old name still resolves its `output.json`.
- **A node has no per-node cwd, and one ported script depended on that without saying so.** The
  YAML gave `build_documentation_context` `cwd: docs_repo_path`, so `build-qa-okf-context.py`
  could pass `None` to `Ostler` and let it discover its root. Under the driver that discovery
  lands on the orchestrating repo, and the packet is diffed against the wrong git tree. Caught by
  the docs local-mode test, fixed in stage B2 by resolving through `find_docs_root(docs_path)` —
  which is what the sibling validator node already did and what the `cwd:` really meant, so the
  fix restores the YAML's behavior rather than changing it. Recorded here because **the class is
  the finding, not the instance**: every YAML node carrying a `cwd:` is a script that may be
  reading the process's location for something the port has to pass explicitly. Stages C and D
  should read each one, and loop 2 should decide whether the driver ought to make this
  impossible rather than merely detectable.
- **`max_review_reworks` is the third inert budget var in `coder`.** Declared once at top level
  (line 132), never in the `review` flow's own vars — so, like `dev`'s `max_validate_reworks`, it
  could not have reached the flow even if something read it, and `gate_review` branches on a
  literal instead. That is three for three: `max_genesis_reworks`, `max_validate_reworks`,
  `max_review_reworks`. The shape is not an accident of one flow, and a loop-2 sweep for
  branch-on-literal-next-to-a-declared-var will find more.
- **`verify-review-resolution.py` hardcodes `docs/specs/<slug>`.** The story spine resolves a spec
  dir through ostler's `spec_path`; this one does not, so a repo whose specs live elsewhere gets a
  pass-through gate instead of a settlement — silently, because "no verdict sidecar" is a legal
  state. Ported as written, since changing it changes which stories the anti-gaming gate binds on.
- **`classify-documentation-context.py` encodes and decodes for no one.** It takes
  `qa_source_roots_json` and returns `documentation_source_roots_json`, both JSON-encoded strings
  crossing a boundary that is now a typed value. Same divergence already recorded for `dev`, now
  seen twice; the port passes `list[str]` and the encoding is gone.
- **`await_operator_review` has no `SCOPE: epic` branch, where `dev`'s equivalent does.** An
  operator who answers a review block with an epic-scoped instruction has it applied as a
  story-level fix. Preserved, because adding the branch is a behavior change — but it is the kind
  of asymmetry that reads as an oversight rather than a decision, and loop 2 should ask.
- **Environment variables read inside nodes are a loop-2 item, per `docs/backload.md`.** The
  working tree carries the rule "using environment variables in nodes and workflow IS
  PROHIBITED — everything needs to be passed by argument or be a workflow parameter". `coder`'s
  nodes currently read `AGENT_REPO_DIR`, `CODER_WORKSPACE` and `CODER_DOCS_PATH` exactly as the
  YAML scripts did, because this loop ports behavior rather than redesigning it. Converting them
  to inputs is a coherent loop-2 change and touches every port.
- **The QA setup gate has no terminal, and in auto mode it is an infinite cycle.** Once
  `max_setup_reworks` is spent, `guard_setup` escalates to the operator gate; the gate's answer is
  applied as a QA fix that rejoins at `build_qa_okf_context`, which walks back down to
  `ensure_stack`, which is still down, which finds the budget still spent, which escalates again.
  Every counter on that cycle is either already at its cap or — `qa_rework_count`, which the fix
  path does increment — read by nothing on it. With `operator_mode=auto` the resolver always
  answers, so nothing breaks it. The YAML was stopped by the engine's global step budget; the port
  is stopped by the driver's transition budget, which at least names the state it died in. Ported
  faithfully and pinned by `test_a_stack_nobody_can_repair_spins_on_the_operator_gate`; bounding it
  is a behavior change and therefore loop 2's. The obvious fix is for the setup-exhaustion arm to
  reach `guard_qa` rather than the plain fix path, so the QA budget actually bounds it.
- **`await_operator_qa` declares a `plan_rework_count` output that nothing produces or reads.**
  `await_operator.py` prints no such key and no branch downstream consults it, so the YAML's own
  `outputs:` list is a no-op that would silently zero the counter if the script ever grew one. The
  port drops it. Recorded as a finding rather than a narrowing because there is no reader to lose.
- **A fifth and sixth inert budget var, in `qa`.** `max_qa_reworks`, `max_context_reworks`,
  `max_plan_reworks`, `max_setup_reworks` and `max_triage_scopes` are all declared at top level and
  all branched on as literals with a "keep in sync" comment — the same shape as `max_genesis_`,
  `max_validate_` and `max_review_reworks`. That is eight declared-but-inert budget vars across
  four flows. They are `ClassVar` ints in the port, which makes the real ceiling the only ceiling.
  The loop-2 sweep this calls for is now unambiguous: **every** `max_*` var in `coder`'s YAML is
  suspect until read.
- **Stage B2 shipped without the prompts it renders, and C3 fixed it.** `review` and `docs`
  reference six prompt files that were never copied into `workhorse_workflows/coder/prompts/`;
  their tests script the agent turn, so a missing prompt file is invisible to them — the engine
  derives the node id from the path's stem and never opens it. All 17 prompts the three flows
  reach are now present. **The class is the finding**: no test in any port so far asserts that a
  prompt a flow names exists on disk, and stage D should add one static check that walks every
  `self.agent(prompt=…)` in the package and stats the file. That is cheap and would have caught
  this at B2.

## What is next

1. **Port `coder`** — loop 1.1's last, deleting nothing. Each port is the
   whole package per that section: `workflow.py` holding only the class, `nodes/` grouped by subject,
   schemas, `paths.py` for the derivations, `flows/` per sub-graph, one entry-point line and one
   console script in `workflows/pyproject.toml`, and tests under `workflows/tests/<workflow>/`
   mirroring the node modules. Take `tests/research/test_workflow.py` as the pattern for what goes
   *inside* a test module — real nodes against a temp git repo, only the agent turn scripted — because
   it is what made the port's claims checkable. `author` is now the closest worked example for
   both of the shapes `research` lacks: `Await` (`gate_*` states) and `handoff` (`flows/`).
2. **Record parity per workflow, here.** Same artifacts and same resume behavior as the YAML for at
   least one real run. Both engines are present for the whole of loop 1.1, so the comparison is
   available; loop 2 will not start without it.

## Open questions

All three are the user's call, all raised and not yet answered, and none blocks stages C and D.

1. **Repair the manifest gap in the engine, in this loop, or leave it for loop 2?** See the
   finding above. It is a `pyflow/run.py` + `engine.py` change, so it is a driver-API-adjacent
   change and therefore the user's call; it also re-validates every port already landed. Leaving it
   means the ports are *structurally* at parity while every prompt that references a skill renders
   a placeholder sentence — which is not a difference any port should absorb silently, hence its
   place here rather than only in the findings.
2. **The package layout note in `docs/backload.md`, found during C1.** It proposes grouping a
   workflow by *flow* — `coder/qa/{flow.py,nodes.py}` plus a `shared/` — rather than the current
   `nodes/` -by-subject plus `flows/`. It is a real improvement and it is also a rename of every
   module in all four ports, so doing it mid-`coder` would churn A, B and C for no behavior change.
   Recommendation: land it in loop 2 as one mechanical move once `coder` is drivable, not now.
   Raised here because it is much cheaper to decide before D than after. (The same file's
   "environment variables in nodes are PROHIBITED" note is already a finding above, and the
   "paths mangling should come from ostler" note belongs with it.)
3. **Keep or restore the one narrowing in `coder/paths.py`** — the dropped fourth rung
   (a walk upward from `__file__`) in the launch-checkout resolution. Under the driver that rung
   can only ever resolve to the installed `workhorse_workflows` package, never the consuming
   repo, so porting it would port a wrong answer. Recorded as a finding; restoring it is one line
   if the user wants byte-parity over correctness here.

## Decisions re-confirmed

Entries here mean an iteration went back to the plan for something it had lost. The plan section
that settled it is named so the next reader can go straight there.

- **The shared `Blueprint` lives in `nodes/_blueprint.py`, not `nodes/__init__.py`** *(step 0, found
  while building)*. The plan says `nodes/__init__.py` "assembles the Blueprint", and it does — it is
  the one import `workflow.py` needs. But the object itself cannot be *defined* there: every node
  submodule decorates against it, so defining it in `__init__.py` makes each submodule import the
  package that imports it. That resolves only because the name is bound before the submodule imports
  run, i.e. by statement order, and ruff's E402 objects to the arrangement that makes it work. A
  three-line private module has neither problem. Every port uses this shape.
- **Typed payload models were removed** *("Rejected along the way")*. Lost across a compaction in
  loop 1's first run and rebuilt as `research/models.py`. This is the entry that motivated the
  ledger. **Settled:** what was rebuilt is *not* the rejected shape — nothing in the file crosses a
  transition, and a transition carries keyword arguments bound against the next state's signature.
  What is there is what the seams require: agent-reply schemas (`self.agent(returns=T)`, whose
  fields are also the output keys the resilience ladder nulls out), node return types, and
  `Program`, the `setup()` residue. Kept, renamed `schemas.py`, docstring rewritten so it no longer
  claims to be payloads between states. Do not re-litigate; the name now carries the decision.
- **A fail terminal under `--dry-run` is an artifact of the stand-ins** *(raised by the port,
  answered by the user)*. Stubbed nodes return blank models, so the machine takes whichever
  branch a blank selects — `research` walked `start → goal_review → halt` and exited 1 on a
  clean preflight, and no workflow with a reachable fail terminal could have dry-run green.
  `run.py` now prints the halted state and exits 0 for `WorkflowFailed` **under `--dry-run`
  only**; the run dir is still marked `fail`, and every other `PyflowError` still exits 1. Note
  the shape: it is a branch *inside* `except PyflowError`, not a handler before it — a
  `raise` from a sibling `except` arm escapes the whole `try` rather than falling through to
  the next one, which is what the first attempt got wrong.
- **The three driver additions `author` asked for were approved, so do not re-ask** *(raised by the
  port, answered by the user)*. Activity is `logger.info(msg, extra={"activity": True})`; activity
  labels are **unprefixed** ("we will not carry over the prefix, we will change groom instead
  later"); `self.agent` takes `cwd`/`add_dirs`. A driver-API change is still the user's call —
  these three are simply already made.
- **The `kit` package forwards through `__getattr__`; it does not re-export** *(step 2, found while
  building)*. workhorse re-executes a script module on **every** node run, so a script's
  `from workhorse_workflows.kit import github_client` re-reads that attribute each time — which is
  exactly what made `monkeypatch.setattr(scriptutil, …)` reach into scripts. A plain
  `from .github import github_client` in `kit/__init__.py` would bind once at *package* import,
  one process-lifetime earlier, and every existing patch would silently stop reaching the script.
  PEP 562 module `__getattr__` keeps the old seam: patch the **defining submodule**
  (`kit.git`, `kit.github`, `kit.workspace`) and both the flat importers and `kit`'s own internal
  callers follow. Corollary, and the reason `kit/github.py` says `git_kit.origin_url(...)` rather
  than importing the name: a helper calls across modules **through the module object**.
