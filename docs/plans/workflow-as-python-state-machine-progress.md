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

**Loops 1 and 1.1 are both done.** All four workflows resolve through `workhorse.workflows`
entry points and run on the driver:

```
author → workhorse_workflows.author.workflow:workflow
coder  → workhorse_workflows.coder.workflow:workflow
okf-builder → workhorse_workflows.okf_builder.workflow:workflow
research → workhorse_workflows.research.workflow:workflow
```

Each has a parity section below.

**Loop 2 is in progress, and as of step 2 no YAML front-end remains.** There is one engine:
`graph/`, `runner/{script,branch,call}.py`, `builtins.py` and `requirements.py` are deleted,
`main.py` is 670 lines of CLI over `run_pyflow`, and a workflow name resolves only through the
`workhorse.workflows` entry-point group. `base-library/workflows/` is deleted too — all 7,719 lines
of graph YAML, its 127 scripts and its 61 prompts. Step 3 took the plumbing that outlived it: a
library is `library/` and nothing else, and farrier no longer owns `.agents/workflows`. Step 4
narrowed the fetch: the cache now holds a sparse checkout of `base-library/` with no `.git`, which
is markdown and YAML and not a line of Python. Step 6 put a retired banner on the last two
documents that still described the format as current.

**Loop 2 is complete** — see "Loop 2 is done" below for the end condition checked rather than
asserted, and the one finding it leaves for loop 3. Next is loop 3, the documentation pass:
the plan's §Migration items 1–5.

The port cost the driver **four additive changes, all in loop 1.1 step 1**, all asked for by
`author`. `okf-builder` and every one of `coder`'s nine stages needed **none** — thirteen
consecutive green steps against a frozen API, which is the strongest evidence available that the
shape is settled.

Ported, counting every graph and sub-graph: **559 YAML nodes → 178 states**, a factor of three.
`author` 166 → 46 across three flows, `coder` 308 → 102 across nine, `okf-builder` 48 → 17 across
two, `research` 37 → 13. **291 end-to-end tests** in `workflows/tests/` (author 155, coder 119,
okf-builder 8, research 9), every one against real nodes with only the agent turn scripted, plus
81 cross-cutting ones — 372 in total. (The YAML engine's own suite is no longer under them; step 1
took it.)

**Loop 2's starting state is at the bottom of this file, and what it has done so far is under
"Loop 2 — the deletion" below.**

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
| 10 | `945e540` | `coder` **stage D1** — the main graph's queue spine: `schemas/queue.py`, `story_status.py` and `nodes/queue.py`, 9 nodes ported from 9 scripts (≈900 lines). Parity checked script-by-script against the sources. No driver change |
| 11 | `f896461` | `coder` **stage D2** — the PR boundary and the backlog drain: `schemas/{pr,backlog}.py` and `nodes/pr.py`, 9 nodes from 10 scripts. Two subprocess layers collapse; the four fix-drain nodes join the filing node in `nodes/backlog.py` behind one bullet-grammar definition. No driver change |
| 12 | `78436af` | `coder` **stage D3** — the `fix` flow: 24 YAML nodes → 9 states, entered directly rather than handed off to, with the `docs` sub-flow running for real inside it. 12 end-to-end tests. No driver change |
| 13 | `7e33233` | `coder` **stage D4** — the main graph: 80 YAML nodes → 27 states, both pyproject lines, 12 end-to-end tests plus a cross-workflow static prompt check (77 sites). Loop 1.1's exit gate. No driver change |

### Loop 2 — the deletion

| Step | Commit | What |
|---|---|---|
| 0 | `d8b0879` | **Prep, no deletion.** The two types `pyflow` borrowed from the YAML engine move out of `graph/` ahead of it: `graph/context.py` → `workhorse/context.py`, and `AgentNode`/`OutputSpec` → `workhorse/runner/spec.py` (`graph/nodes.py` re-exports them while the YAML node union still exists). This is blocker (1) of §2 below, cleared. Also fixes a red baseline inherited from loop 1.1 — see below |
| 0.1 | `e1f92f5` | **The one authorized driver change, and still no deletion.** The context manifest reaches a pyflow prompt: `workhorse/manifest.py` (moved out of `main.py`), a `manifest` seat on `RunEnv`, `run_pyflow(context_manifest=…)`, and the `--context-file` passthrough. §4 item 1, cleared |
| 2 | `cc8b850` | **The YAML itself.** `base-library/workflows/` deleted — 213 tracked files, the four `workflow.yaml` (7,719 lines) and 127 remaining scripts. One thing was carried out first: `research`'s program scaffolder. List item 2, done |
| 1 | `20f5183` | **The YAML engine.** `graph/` and `runner/{script,branch,call}.py` deleted, `main.py` 1,667 → 670 lines, `testing.py` 575 → 103, and with them the 63 base-library workflow test files, 10 workhorse test files and the `test-workflows` make target. List item 1, done — and it took list item 2's `requires:` half with it |
| 3 | `81287c4` | **The plumbing.** `is_library_dir` is now `(path/"library").is_dir()` — `workflows/` is no longer a library's content — and farrier stopped owning `.agents/workflows`: gone from `remove_targets` and from the `--check` extra-file scan, taking `should_skip_workflow_file`/`WORKFLOW_SKIP_PARTS` with them. List item 3, done |
| 4 | `5461e89` | **The fetch.** `_clone_into` is a sparse `base-library/`-only checkout (`--filter=blob:none --sparse`, `sparse-checkout set --no-cone`) that records HEAD in a `.commit` sidecar and deletes `.git`. 628K→240K, and nothing fetched is executable. Fails closed: no fallback to a full clone. List item 4, done |
| 6 | `5d10de4` | **The last two false documents.** `docs/features/workhorse/workflow-format.md` and `workhorse/docs/WORKFLOW.md` (482 lines) carry a retired banner and are reframed in the past tense — corrected, not rewritten; their successors are loop 3's. List item 6, done, and with it loop 2 |

**The entry gate held.** All fourteen `### Parity` sections are present and behavioral, so every
workflow whose YAML this loop deletes has recorded evidence. Deletion may proceed.

**The baseline was red on arrival, and not from anything loop 2 did.**
`workhorse/tests/test_library_layers.py` named its fixture workflow `coder`, and since loop 1.1
`coder` is a real `workhorse.workflows` entry point — which by design wins over every library
layer, so four of its six tests were resolving the entry point instead of the layering they exist
to test. Renamed to `acme-flow`, a name no distribution ships. Worth knowing because it is the
shape of the next such break: *any* test that uses a real workflow's name as a fixture now tests
the entry-point branch.

**The engine deletion could not be one commit, and it was not.** `make test` ran
`base-library/workflows/*/tests` **in-process against the YAML engine** via
`workhorse.testing.WorkflowRun`, so deleting the engine is only green if those suites go with it —
they are on the deletion list (§1, "…their `tests/`"), just one bullet later than the engine. So
step 1 took the engine, the YAML-engine tests, the base-library workflow test suites and the
`test-workflows` make target together. Step 2 is the rest of `base-library/workflows/`.

**Before that commit, one thing went to the user** — §4 item 1, the context manifest, which was no
longer just a parity gap: 13 ported prompts under `author/` and `coder/` call `instruction_ref`,
`isUsingInstruction` and `template.*`; only `main.py` ever loaded the manifest that resolves them;
`run_pyflow`/`RunEnv` had no seat for one; and `templates.py` suppresses its own unresolved
warning when no manifest is present, so the degradation was **silent** — `instruction_ref('go')`
renders as the prose placeholder and every stack-specific guidance block drops out. Deleting
`main.py` would have removed the reference implementation and made `--context-file` permanently
inert. That is a driver change, which loop 2's work order excludes, so it was the user's call and
not a fix to improvise.

**The user's answer: wire it into pyflow first** — copy `main.py`'s behavior while it still
exists, then delete. Landed as step 0.1, the one authorized driver change in this loop:

- `workhorse/manifest.py` — `load_context_manifest` / `build_manifest_context` / `BACKEND_SKILL_DIR`,
  moved verbatim out of `main.py`. Both engines load a manifest, so it belongs above either one; the
  move is what lets it survive `main.py`. `main.py` binds it back under its old private name, which
  is also the seam two `test_packaged_workflows.py` tests patch.
- `RunEnv.manifest` — the **outer** layer of an agent turn's render context, `{**manifest,
  **args}`. A state that binds `repo` gets its own; an empty manifest adds no keys, so a
  manifest-free run still renders exactly its arguments. Two tests in `test_pyflow.py` hold both
  halves.
- `run_pyflow(context_manifest=…)`, fed from the existing `--context-file` resolution in `main.py`,
  so `workhorse run <name>` and the `workhorse-<name>` console scripts get it from the one parser.
- The skill/prompt reference preflight (step 4's, `references.py`) now runs for Python workflows
  too: a warning on a real run, an exit code under `--dry-run`, and skipped entirely when the run
  carries no manifest. `test_pyflow_graph.py` covers all three.

Green: `ruff check .`, `make test`, `make check-public`. No port changed — the seat is additive and
every one of the 372 tests still passes without touching a workflow.

#### Step 1 — the engine

**The CLI was not lifted.** §2 said the CLI has to move out of `main.py` into `workhorse/cli.py`
before `main.py` can go. It does not: `main.py` can lose its engine half and keep its name, and
keeping it is strictly cheaper — the alternative repoints `workhorse/__init__.py:1`,
`pyflow/registry.py:180`, four console-script entry points and a `"workhorse.main"` string in
`test_logsetup.py`, all for a rename. `main.py` is now 670 lines and holds only argument parsing,
run-id/resume resolution, `dot`, `config` and `version`; every `run` invocation ends in
`sys.exit(run_pyflow(...))`.

Deleted outright: `graph/{loader,nodes,dot}.py` (537 lines), `runner/{script,branch,call}.py` (445),
`builtins.py` (20), `requirements.py` (228), `workhorse/tests/test_requirements.py`, and 10 dead
workhorse test files (`test_dot`, `test_branch_guardrail`, `test_call_node`, `test_flows`,
`test_forbid_shell`, `test_gas_tank`, `test_labels`, `test_library_layers`, `test_script_inprocess`,
`test_interrupt`). On the base-library side: 63 files — the `tests/` trees of `author` (incl.
`author/surveyor/`), `coder` and `okf-builder`, plus three `pytest.ini`. The root `Makefile` loses
the `test-workflows` target that ran them.

**`graph/dot.py` was deleted, not rewritten.** The work order says "rewrite `graph/dot.py` against
the new model", but the new model already had one: `pyflow/dot.py` + `pyflow/graph.py` landed in
step 6 of loop 1. `workhorse dot` now renders through those, and the YAML renderer is a second
implementation of a thing that exists.

**What the deletion took with it, none of it on the list:**

- `runner/call.py` **is** the `call:` node and imports `graph/nodes.py::CallNode`; `builtins.py`'s
  only importer was `runner/call.py`. Both die *because* `graph/nodes.py` does — forced, not chosen.
- `requirements.py` implements `Graph.requires`, which the loader parsed. It could not outlive the
  loader, so **list item 2's `requires:` half landed here, one commit early.**
- `RunConfig.script_runner` / `get_script_runner()` / `ScriptRunner` and `RunConfig.gas` /
  `_configured_gas()` / `WORKHORSE_GAS`. Both looked like driver API and neither was: a repo-wide
  grep puts every consumer inside the `script:` dispatch, `testing.py`, `_GasTank` and the deleted
  tests. `config_run.py` is 147 lines and keeps `AgentResilience`, `resilience`, `max_runtime_s`,
  `backend_factory`, `get_backend()`.
- `testing.py` 575 → 103: `WorkflowRun`, `RunResult`, `InProcessScriptRunner`, `_MockBackend`,
  `assert_step_output`, `assert_prompt_contains`, `assert_command_called`. What a callable flow
  still needs is `make_git_repo`, `assert_file`, `assert_file_contains`, `assert_json_file`.

**Visible CLI surface that changed** — the operator-facing part of this commit:

- `--workflow <path>` is gone. A workflow is a Python package, so `--workflow` takes a **name**, and
  a name resolves in exactly one place: the `workhorse.workflows` entry-point group. The library is
  no longer consulted for workflows at all, which is what makes list item 4 (the sparse checkout of
  `library/`) true rather than aspirational.
- An unknown name is answered with the sorted list of installed ones (`packaged.installed_workflow_names`).
- `--pin` / `--leaf` no longer parse. A state machine's branches are ordinary Python; there is no
  declared branch variable to pin. Give a mode its own flow if its diagram should stand alone.
- The "an installed package shadows a library layer" stderr warning is gone with the shadowing.
- **One regression, found and fixed inside this commit.** Refusing a zip-imported workflow used to
  happen at resolution, in `PackagedWorkflow.workflow_dir()`; under the driver it lives in
  `Registry.directory()`, which is called lazily at the first prompt render. Deleting the old path
  would have turned "this wheel is packed wrong" into a `TemplateNotFound` several nodes into a run.
  `_packaged_registry` now calls `target.directory()` eagerly and exits 1 with the message. Judged an
  error-handling hole opened by the deletion, not a driver-API question, so it was not escalated.

**Deliberately kept, all loop-3 cleanup, none of it on this loop's list:** otel's `workhorse.gas`
instruments and `gas_level()` (collector-facing, tested, now inert); `ArtifactWriter.read_done` and
`write_branch`; `PackagedWorkflow.workflow_dir()`. Also `scriptutil.py` — §1 lists it as deletable
and it is not: ~20 modules under `workflows/src/workhorse_workflows/**` still import it.

**Docs corrected, not rewritten**, per the work order's last bullet — `workhorse/README.md`
(the whole `workflow.yaml` schema section replaced with the Python-package layout, the project-layout
tree and "how the controller works" rewritten around `pyflow/driver.py::drive`, the `WorkflowRun`
testing story replaced with `RunEnv.run_agent` + `Registry.override`, every stale
`--pin`/`--leaf`/`--workflow <path>`/`requires:`/library-layer reference removed) and
`workhorse/CLAUDE.md` (the graph-walk description). `docs/GUARDRAILS.md` got the env-var table
(`WORKHORSE_SCRIPT_INPROCESS` and `WORKHORSE_GAS` out) and the node→turn vocabulary. The four
remaining "YAML" mentions across both are two historical "the retired YAML engine" sentences and two
`compose.yaml` filenames.

**Known-dangling references this commit creates**, to sweep in loop 3 — they break no test, because
ostler's own suite uses fixtures: `docs/features/workhorse/concepts/{gas-tank,workflow,run-flow,
testing,artifact-writer,stream-subprocess,run-agent,pyflow-driver}.md`,
`docs/features/workhorse/flows/*.md`, `docs/features/workhorse/run-artifacts.md`,
`docs/plans/workhorse-otel.md`, `workhorse/docs/WORKFLOW.md` (now unlinked from the README, still
linked from GUARDRAILS), and both copies of the scripting skill
(`.claude/skills/stablemate-workhorse-scripting/SKILL.md`,
`base-library/library/skills/stablemate/stablemate-workhorse-scripting/SKILL.md`), which still show
`from workhorse.testing import WorkflowRun, assert_step_output`.

#### Step 2 — the YAML

`base-library/workflows/` is gone: 213 tracked files, the four `workflow.yaml` (7,719 lines), 127
scripts, 61 prompts, 15 docs and the directory's own `README.md`/`CLAUDE.md`. **The 7,719 lines are
accounted for** — every one of them is a state in a `workhorse_workflows` package, with a `### Parity`
section above saying how far the evidence goes.

**The prompts were diffed before deleting**, as §1 required, and the drift is one systematic thing
rather than lost content. Of 61: 33 byte-identical, 22 drifted, 6 in the port with no base
counterpart, **0 in the base with no port counterpart**. The drift is the port removing the YAML
engine's outer node-key wrapper from the reply contract — `{"review_epics_result": {...}}` became
`{...}`, because `self.agent(returns=Model)` validates the object itself. The two larger ones,
`author/prompts/resolve-{integrity,operator}.md`, carry the `CONSUMED` finding's resolution: the
`STATUS: ANSWERED` / `STATUS: AWAITING_OPERATOR` sentinel the YAML gate parsed out of the operator
file is now the reply's own `decision` field, and the file is appended to rather than stamped. In
every case the base copy is the older one.

**One thing was carried out rather than deleted, and it is the only such thing.**
`research/scripts/new_program.py` (119 lines) plus `research/templates/` — the program scaffolder.
It was never a graph node, which is why no port ported it, and it is the **only producer of the
input the workflow consumes**: `load_config` and the gate-loop prompts read a `program.yml`,
`PROGRESS.md` and `<gate>_program.md` in exactly the shape it stamps. Deleting it would have left
`research` runnable with nothing to run it on. Moved verbatim to
`workflows/src/workhorse_workflows/research/scaffold/` (one line changed: `TEMPLATES` is now
`parent/"templates"`), invoked as
`python -m workhorse_workflows.research.scaffold.new_program`, and verified end-to-end against a
temp repo. A sweep for others found none: the only other graph-unreferenced scripts are the six §1
already lists as dead plus three coder modules imported by their siblings.

**The forced companion change.** `scripts/check_public.py::check_base_stands_alone` asserted "the
base ships no workflows" as a *failure*, so deleting the directory turns `make check-public` red.
That clause is list item 3's first half, pulled forward for exactly the reason `requires:` was
pulled into step 1 — a green tree does not wait for its own bullet. The check now reports
`ok: 9 base skills resolve with no overlay configured`; the second half of that item
(`is_library_dir`, farrier's `.agents/workflows` cleanup) landed as step 3.
`workflows/pyproject.toml`'s entry-point comment, which claimed the base kept a runnable YAML
`research`, was corrected in the same commit.

**Farrier's workflow pipeline was not touched and is not dead.** `renderer.py`, `sources.py`,
`launcher.py` and `outputs.py` still resolve, select, materialise and mount workflow *directories*
from a layer. The base simply ships none now; an overlay may still. Narrowing that is not on this
loop's list.

**List item 5 closed with this commit rather than after it.** `await-operator.py` lived *inside*
`base-library/workflows/`, and there were three copies, not two: `author/scripts/` (280 lines),
`author/surveyor/scripts/` (275) and `coder/scripts/await_operator.py` (323) — 878 lines of ctypes
inotify, deleted unported as loop 1.1 intended, with the driver's polling `Await` as the
replacement.

#### Step 3 — the plumbing

Two small deletions with one meaning: a library is `library/`, and `.agents/workflows` is nobody's.

**`is_library_dir` accepted "contains `library/` OR `workflows/`".** That "or" was written when a
workflow was a directory of YAML a library could ship, so a base holding only `workflows/` was a
usable base. It cannot be one now — a workflow is a Python package resolved through an entry-point
group, and a directory holding only `workflows/` carries no library content at all. Left as-is it
was worse than stale: `set-base` would have silently accepted such a directory and handed every
tool an empty layer. It is now `return (path / "library").is_dir()`, and the three error strings
that recited the old rule (`workhorse/main.py`, `farrier/cli.py`, `farrier/layers.py`) say
`library/`. Two tests asserted the old "or" directly — `core/tests/test_discovery.py` and
`farrier/tests/test_config_resolution.py` — and both now assert its opposite; core's shared
`_make_base` helper and `test_base_cache.py`'s `_fake_clone` were building their fixture libraries
out of `workflows/`, which is what made this a seven-test failure rather than a one-line change.

**Farrier's `.agents/workflows` cleanup.** Farrier rendered a workflow's tree there until the
front-end retired; grep confirms it has written nothing into it since, so both remaining mentions
were legacy. `remove_targets` no longer deletes it, and `check_outputs` no longer scans it — that
scan was the worse of the two, since a leftover from an older install would be reported `extra:`
and no amount of re-rendering would clear it. `should_skip_workflow_file` and
`WORKFLOW_SKIP_PARTS` existed only to make that scan tolerable and went with it, along with their
`install.py` re-exports.

**A finding, recorded rather than fixed.** `renderer.py:439-449` still validates a `workflows:`
selection against `find_in_layers("workflows", name)`. The mechanism works, but the base ships no
`workflows/` directory any more, so a base-only install can no longer name a workflow at all — the
launcher scaffolding it gates (`agents.mk`, the compose override, the context manifest) is
unreachable without an overlay that still has one. That row of the plan's table is not on loop 2's
list, so it stays; `farrier/docs/LAYOUT.md` now says so plainly instead of describing a copy step
that no longer happens.

Corrected in the same commit, all of it prose that had gone false: `docs/features/farrier/farrier.md`'s
`--check` description, `farrier/docs/LAYOUT.md`'s `workflows/<name>/` section, and the three places
in `core/` (`base_cache.py`'s module docstring, its `BASE_SUBPATH` comment and its stale-cache
warning; `discovery.py`'s `CHECKOUT_SUBPATH` comment) that listed `workflows/` as part of the
library payload.

#### Step 4 — the fetch

The last thing treating the base as a repository. `_clone_into` cloned the whole of stablemate into
`~/.cache/stablemate/library` and left `.git` behind, so `cached_commit` could `rev-parse` it. That
put every `.py` in this repo — and its git history — inside the cache of anyone who ran a workflow
without a checkout. It now clones `--depth=1 --filter=blob:none --sparse`, sets
`sparse-checkout set --no-cone /base-library/`, checks out, writes HEAD to a `.commit` sidecar and
`rmtree`s `.git`. Verified against the real remote: **628K → 240K**, exactly `base-library/` plus
`.commit`, no `.git`, and `find base-library -type f ! -name '*.md' ! -name '*.yml'` is empty —
**nothing fetched is executable.** That claim is the point of the narrowing and it is what step 2
earned; while the base shipped 127 `scripts/*.py` that ran under `sys.executable`, a narrow fetch
would have been a false reassurance.

Three details that are load-bearing rather than incidental:

- **`--no-cone`, not the default cone mode.** Cone mode always materialises the repository root as
  well — `pyproject.toml`, `Makefile`, `uv.lock`, `.mcp.json`. Inert, but not documents, and the
  first real fetch produced exactly that (628K) before the switch. "Only the library" should mean
  it.
- **`--filter=blob:none` is what makes it a *transfer* saving.** Without it git sends every blob in
  the commit and the sparse checkout merely declines to write them.
- **It fails closed.** A git too old for `sparse-checkout` (< 2.25) gets no library at all rather
  than a full clone, because a silent fallback would drop the posture without saying so.
  `test_a_failed_sparse_checkout_does_not_fall_back_to_a_full_clone` pins that.

`cached_commit` reads the sidecar instead of shelling out, which also makes a hand-assembled cache
(an air-gapped host copying the directory in) able to say what it holds; a pre-narrowing cache with
`.git` but no sidecar reads as unknown rather than as a stale sha. `core/tests/test_base_cache.py`
is 25 tests, two of them new and specifically about the posture — its `_fake_clone` now builds what
a real fetch leaves rather than a repo.

The plan says "a sparse checkout of `library/`"; the target here is `base-library/`, the whole
payload. `scaffolds/` lives beside `library/` under it and the same plan keeps scaffolds a
farrier/library concern, so narrowing to `base-library/library/` would have deleted a feature under
cover of a fetch change.

Corrected in the same commit, all of it prose the narrowing or the earlier deletions had made
false: the root `README.md` (workhorse "drives a YAML workflow graph"; the base-library row listing
`workflows/`; the whole `requires:` section, which now says the tools are `[project.dependencies]`
on `workhorse-workflows` and that `requires:` has no successor), plus a `workhorse-workflows` row
in the package table and the `pipx inject` line that makes `workhorse run <name>` actually resolve.
`base-library/README.md` was the worst of them — it advertised `workflows/` as the payload,
"the Python scripts workflow nodes run", `git rev-parse` against the cache, and a `requires:`
schema link to a deleted doc. Also the two `pytest-xdist` comments naming a `pytest.ini` that went
with the YAML tree, and `workhorse/README.md`'s per-workflow-docs path.

#### Step 6 — the last two false documents

`docs/features/workhorse/workflow-format.md` (164 lines) and `workhorse/docs/WORKFLOW.md` (482)
are the same file at two levels of detail: a complete schema reference for a schema with no
parser. Both now open with a banner saying the format is deleted, that `workhorse run <name>`
will not read a `workflow.yaml`, that a workflow is a `Workflow` of decorated methods returning
`Continue`/`Done`/`Await` resolved through the entry-point group, and that the body is the record
of what the four shipped workflows were ported *from*. The bodies are untouched below that.

That is deliberately a correction and not a rewrite. The plan assigns both successors to loop 3
(§Migration items 2 and 3) and says of this one that loop 2 "only corrected far enough not to be
false" — writing the Python-API reference mid-deletion is how it gets written from memory instead
of from what loop 2 actually built. Two details the banners record because they are the parts
readers will otherwise assume changed and did not: checkpointing survives, rekeyed from a node id
to `(state, params)`; and GUARDRAILS' resilience knobs are untouched, because they sit under the
agent turn, which both engines drive identically.

`workflow-format.md`'s heading anchors are left alone even where the words have gone stale
(`## Sample (load-valid)`), because the `concepts/` and `flows/` pages link into them and loop 3
is rewriting that whole book — breaking fifty inbound anchors to fix one adjective is a trade in
the wrong direction. The two scripting-skill copies still call WORKFLOW.md "the authoritative
schema"; the banner answers them on arrival, and they are on loop 3's list.

(`base-library/workflows/README.md`, the third file on the docs-correction bullet, was deleted
with its directory in step 2 — the strongest correction available.)

### Loop 2 is done

The end condition, checked rather than asserted:

- **No YAML front-end remains.** `git ls-files | grep -c workflow.yaml` → `0`.
  `workhorse/workhorse/graph/` does not exist.
- **All four resolve through `workhorse.workflows` and still run.** The entry-point group loads
  `author`, `coder`, `okf-builder`, `research`; all four `workhorse run <name> --dry-run` green.
- **The 7,719 lines are accounted for.** Every one is a state in a `workhorse_workflows` package
  with a `### Parity` section above. One thing was carried out rather than deleted and is named:
  `research`'s program scaffolder. 878 lines of `await-operator.py` were deleted unported, as
  intended, with the driver's polling `Await` as the replacement.

**One finding for loop 3, recorded and not fixed here**, since fixing it meant improvising on
farrier mid-deletion: `renderer.py:439-449` still validates a `workflows:` selection against
`find_in_layers("workflows", name)`. The base ships no `workflows/` directory now, so a base-only
install cannot name a workflow and the launcher scaffolding it gates is unreachable without an
overlay that still has one (step 3).

**And one non-finding, checked so loop 3 does not have to.** The plan flags `labels:` and per-node
`power:` as YAML blocks that are "now something else — and if loop 2 built nothing for them, that
is a finding." Both exist: `Workflow.labels()` is a hook the driver renders per state onto the
activity record (`pyflow/driver.py:296`, `RunEnv.labels`), and `power` is a keyword on
`self.agent(...)` that reaches the turn's budget (`pyflow/engine.py:273`) — it landed in loop 1's
`5d3f89d`. Loop 3 documents them; it does not need to build them.

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

### Parity — `coder`, stage D1 (the queue spine)

Stage D lands in four: **D1** the queue spine (here), **D2** the PR/CI/merge and backlog nodes,
**D3** the `fix` flow and its tests, **D4** the main graph, the entry points and the
workflow-level parity record. D1 has no graph to drive, so the claim here is node-level, made
the same way C1's was — every script read end to end against its port.

- **Nine scripts, nine nodes, and the mapping is one-to-one.** `init-base` → `init_base`,
  `branch-story` → `branch_story`, `select-next-epic` → `select_epic`, `branch-epic` →
  `branch_epic`, `select-next-story` → `select_story`, `flag-epic-blocked` →
  `flag_epic_blocked`, `prune-epic` → `prune_epic`, `commit-story` → `commit_story`,
  `flag-qa-failure` → `flag_qa_failure`. No collapses and no splits: these are the states the
  main graph steps through between sub-flows, so each is already at state granularity.
- **The tri-state survives, and it is the one that matters.** `select_story` returns
  `story_outcome` (`story` | `done` | `blocked`) as a string defaulting to `blocked`, per the
  rule `schemas/ci.py` settled. This is the field whose conflation merged an epic with 20 of 21
  stories unbuilt; every one of the eight "no story" exits keeps its own distinct `reason`
  string, quoted from the script.
- **Every legacy fallback is ported intact.** `epics-todo.json` in `select_epic` and
  `prune_epic`, `dependencies.json` with all four of its sentinels in `select_story`, and
  `prune_epic`'s explicit-sidecar precedence — none was narrowed, including the sidecar argument
  no graph passes.
- **The only non-zero exit becomes the only raise.** `branch-epic.py` printed `{"error": …}` and
  exited 1 on a failed checkout; `branch_epic` raises `WorkflowFailed` with the same message.
  Every other script's `emit(...)`/`sys.exit(0)` is a returned model.
- **`SPEC_DIR` was dead configuration, and is now a parameter.** `branch-story.py` read the spec
  dir from `os.environ.get("SPEC_DIR", …)`; nothing in the workflow set it, so the default was
  the behavior. It is a defaulted argument now — same behavior, visible at the callsite.
- **Not demonstrated:** any of these under the main graph, which does not exist until D4. The
  `flag_qa_failure` PR comment reaches GitHub and is seamed, as everywhere else in this port.

### Parity — `coder`, stage D2 (the PR boundary and the backlog drain)

Ten scripts, nine nodes. Node-level again — the graph that drives them is D4's — and checked the
same way: every script read end to end against its port, and the four drain nodes additionally
run for real, in sequence, against a temp repo (draw → seed → re-seed → block → dry draw →
prune), because they are the group whose contract is a file format shared with a node that
already shipped.

- **Two process layers collapse, and nothing else about the PR path changes.** `open-pr.py` was a
  seventeen-line `runpy.run_path` harness that ran `gh-open-pr.py` in-process with a swapped
  `sys.argv` and stdout redirected to stderr, purely so the helper's prints could not corrupt the
  caller's JSON envelope. `gh-open-pr.py` then spawned `push-epic.py` as a **subprocess**, with
  `GH_TOKEN` injected into its environment so the child could resolve the credential the parent
  already held. Both are gone: `_open_epic_pr` is a private function of `open_pr`, and the push is
  a direct call to `push_epic_branch`, which resolves its own token from the same repo root. Same
  two-layers-gone story `push-ci.py` told in stage A — and it also settles the environment rule
  for this group: no node here reads an environment variable.
- **`gh-open-pr.py` is not a node, deliberately.** It emitted nothing — it is entirely side
  effects — and no graph references it. A node whose output nothing reads is a node the run record
  cannot explain, so it folds into the node that always called it rather than becoming a second
  state.
- **The `main` default is not applied to a blank, in three of four scripts.** `open-pr.py`,
  `gh-open-pr.py` and `merge-pr.py` all read `sys.argv[2] if len(sys.argv) > 2 else "main"`, and
  the YAML always passed the argument — so an unrendered `base_branch` arrived as `""` and stayed
  `""`. Only `open-story-pr.py` coerced (`base = base or "main"`). The port reproduces the
  asymmetry rather than smoothing it: tidying it is a narrowing, and this loop narrows nothing.
- **`merge_status` stays a string, and it is the second genuine tri-state in this port.**
  `decide_merge`'s `default:` arm is `guard_merge` — the pessimistic one — so a blank must route
  the way `failed` does, which a pair of bools cannot express. Written as `if status in (...)` with
  the blank's arm named, per the rule `schemas/ci.py` settled. `story_pr` stays a string for a
  different reason: nothing branches on it, but it is a *report*, and collapsing it would lose "I
  opened one" against "one was already open".
- **The two give-up banners become `logger.warning`.** `flag-ci-failure.py` and
  `flag-merge-failure.py` printed `"=" * 60` operator blocks to stderr. The banner text is
  preserved verbatim, including the "expected, NOT a crash" line; only the channel changes, because
  the run record is the operator-facing channel now and a stderr block survives only as long as the
  terminal it scrolled past. Their two bodies differed only in wording, so the PR-comment half is
  one `_comment_on_pr` helper.
- **The four fix-drain nodes go into `nodes/backlog.py`, not a new module.** `BACKLOG_ID_RE` is
  declared identically in four of the five backlog scripts and `## Filed by coder` in two. That
  repetition is not incidental: a drain that parsed bullets differently from the filer would
  silently skip items the filer wrote. One definition of each now serves all five nodes, which is
  the only way to make that drift impossible rather than merely unlikely.
- **The one name collision is kept apart.** `seed-fix-story.py`'s `kebab` turns a *sentence* into a
  bounded 60-char slug; `append-backlog-item.py`'s `kebab` sanitizes an already-chosen *id* and
  keeps `.` and `_`. Same name, different jobs — the port keeps both, as `_fix_slug` and `kebab`.
  Merging them would have changed one of the two behaviors.
- **`seed-fix-story.py`'s four `scriptutil.die(…, code=2)` calls are the only raises here.** They
  become `WorkflowFailed` with the same messages. Every other exit across the ten scripts was an
  `emit(...)`/`sys.exit(0)` and is a returned model.
- **The drain's idempotence is demonstrated, not asserted.** Re-seeding the same bullet reuses the
  existing story (`reusing (idempotent)`) and leaves its written sections byte-identical;
  `mark_fix_blocked` on an already-annotated bullet reports `marked=True` without writing; the
  blocked bullet is then invisible to `select_fix_item` and still present in the file for a human.
  All four observed on a real temp repo with a real ostler book.
- **Not demonstrated:** every GitHub call — `create_pull`, `merge`, `create_issue_comment`,
  `get_pulls` — which is seamed here as everywhere else in this port, and the story-mode multi-repo
  PR fan-out, which needs the workspace fixture D3's tests build.

### Parity — `coder`, stage D3 (the `fix` flow)

Twenty-four YAML nodes (lines 3605–3893) become nine states, and this is the first stage of D with
a graph to drive, so the claim is behavioral again rather than node-level: **12 end-to-end tests,
real nodes, only the agent turn scripted**. The backlog file, the seeded story, the code repo's
branch and its git log are all read back off disk after the run.

- **The whole loop runs, and the artifacts are the YAML's.** One drained item produces
  `docs/epics/fixes/stories/<slug>/story.md` carrying the bullet as its single acceptance
  criterion, the bullet gone from `## Filed by coder`, and one commit `fixes: <slug>` in the repo
  the plan named. Five agent turns exactly: `plan-story`, `implement-plan`, `qa-story`,
  `document-story`, `review-story-documentation`.
- **`commit_fix_item.next` really is the draw.** Two backlog items drain in one run as two full
  iterations and **two commits** — not one squashed at the end. That commit-per-item rule is the
  whole difference between this flow and the main graph's nested copy of the same nodes, and it is
  now a test rather than a docstring.
- **The `docs` handoff is exercised, not stubbed.** `seed_fix_story` creates `docs/epics/fixes/`,
  which is a `MANAGED_DIRS` entry, so the sub-flow's OKF pre-gate answers `yes` and the flow spends
  both of its turns for real, taking the `semantic` route because the code repos sit outside the
  docs worktree. A blocked reviewer raises out of the sub-flow, across the handoff boundary
  (`Engine.handoff` does not catch), and out of the fix flow — which is `fix_documentation_failed`,
  the `type: fail`, reached by the arm that reaches it.
- **The retry is one, and the notes cross.** `check → apply_once → recheck`, with
  `apply-qa-fixes` receiving `check`'s verdict verbatim. This is the threaded-argument rule under
  test: `qa_notes` was `get_node_output('check_fix','qa_result').notes` in the YAML, and agent turns
  are not nodes here, so it rides a `Continue` kwarg. A second failure flags rather than retrying.
- **Both flag arms leave the bullet in place, annotated.** A blocked plan flags without spending an
  implement or QA turn at all; a second QA failure flags after exactly one retry. Both write
  `(blocked: …)` in the line, and `select_fix_item` skips it on the very next draw — which is what
  keeps a permanently stuck item from spinning the drain.
- **Resume lands on `check`.** A run killed mid-`qa-story` resumes at `state="check"`,
  `flow="Fix"`, and the resumed run re-draws nothing, re-plans nothing and re-implements nothing —
  it spends one QA turn and finishes. Same shape as every other resume test in this port.
- **Three divergences are preserved and pinned by tests, not smoothed.** (1) `implement_fix.next`
  is `check_fix`, so a plan dispatching two services gets **one** implemented and is then QA'd —
  `flows.dev` loops back to its layer selector and this flow does not. (2)
  `branch_fix_code_repos` is called with `spec_dir` alone, so the branch defaults to the docs
  repo's *current* branch and the code repos stay on `main` — consistent with "commit onto the
  current branch, no push, no PR", and asserted as `branched == []`,
  `already_on_branch == ["api"]`. (3) There is no `stamp_specs` after the plan turn, so a drained
  fix's plan is not registered as an OKF Concept. All three read more like omissions than
  decisions; all three are the YAML's wiring and stay.
- **The prune happens before the documentation.** `prune_fix_item.next` is `document_fix_item`, so
  a run that dies in documentation has already taken the bullet off the backlog while leaving the
  work uncommitted — the failed item is not re-drawn next run. Preserved, tested, and on the
  findings list below.
- **`refuel: fix_bullet_id` has no counterpart.** The drain is unbounded in the YAML and bounded
  here by the transition budget — the same loop-2 design question `okf-builder` raised.
- **Not demonstrated:** the `local` documentation route (the tests take `semantic` by construction,
  so no real `ostler qa context` subprocess runs in this suite), and a drain against a book with a
  populated id ledger — `seed_fix_story` self-creates the `fixes` bucket on an empty one.

### Parity — `coder`, stage D4 (the main graph)

The last stage of the loop. Eighty YAML nodes (lines 191–1348) become **27 states**, and `coder`
now resolves through `workhorse.workflows` like the other three. The claim is behavioral: **12
end-to-end tests driving the real graph**, plus a static sweep that covers all four ports at once.

- **The whole loop runs, on real nodes.** One epic of one story walks `select_epic → select_story
  → prepare → dev → review → document → qa → drain → finalize → commit → select_story → open_pr →
  ci → merge → select_epic → Done`, and what is read back off disk afterwards is the YAML's own
  artifacts: the story stamped `status: QA passed` in its front matter and `- **Status**: QA
  passed` in its body, the epic gone from `docs/epics/index.md`, the work committed as
  `EPIC-1: STORY-1`, the status stamp as a separate scoped commit behind it, and a clean tree.
- **`docs` runs twice per story and that is not a duplicate.** The story's own documentation pass
  and `final_docs` after the drain are separate states, because the second exists so a fix drained
  behind the story is in the book before the single commit that covers both. Asserted as
  `["Dev", "Review", "Docs", "Qa", "Docs"]`, since collapsing them is the obvious wrong
  simplification and nothing else in the graph would notice.
- **The five sub-flows are stand-ins in this file, and the handoff boundary is not.** Each has its
  own end-to-end suite (`dev` 16, `review`/`docs` 25, `qa` 26, `fix` 12, the three small ones 28),
  so re-running them from the top would test them twice and this graph once. A stub is a real
  `Workflow` subclass handed to the real `self.handoff`: constructed with the real keywords by a
  model that forbids extras, driven by the real driver, recorded under the real node id. A keyword
  the graph passes that a flow does not declare still fails here — the half of the boundary a
  flow's own suite cannot check. Every stub replies with the flow's real result model, because
  `DevResult.status`, `QaFlowResult.triage_scope` and `DocsResult.status` are what the graph
  branches on.
- **The run-global counter is under test, both ways.** Three stories in a row that commit nothing
  raise `WorkflowFailed`; three that each land a commit walk the whole epic to the PR. That is
  `zero_diff` threaded through eight states across the epic boundary, which is the noisiest thing
  in this port and now the best-pinned.
- **The triage budget survives a rescope.** A `qa` verdict of `rescope` goes back to `dev` and
  re-enters QA carrying what the first entry spent (`[0, 1]`), with `prepare` — where the budget is
  seeded — entered once for the two QA entries. That is the reason `init_triage_counter` is in
  `prepare` and not in `qa`, now asserted rather than commented.
- **Story mode is a separate path end to end.** `mode=story` cuts its own branch in `start`, never
  touches the queue (`select_epic` and `open_pr` have no run directory at all), and ends at
  `open_story_pr` on the branch `branch_story` recorded — read back from that node rather than
  re-derived from the slug. Handed a bare slug and no epic, every handoff still receives `EPIC-1`,
  which is the story-side of the two epic disjunctions doing its job.
- **The CI escalation is reachable and it escalates.** With CI red, the loop spends exactly three
  `repair_ci` attempts (four polls), writes its questions to
  `docs/epics/<epic>/ci-operator-context.md` naming the spent budget, waits, and resumes on the
  operator's answer with the budget reset — a fifth poll, green, then merge. `operator_mode` is left
  at `auto` deliberately: this gate does not consult it, per the YAML's own comment on the variable,
  so the escalation is reachable in the default configuration. This is the one place a node is
  seamed: `poll_pr_checks` is replaced by a node of the same name stamped by a test-local blueprint,
  because offline it can only ever answer `unavailable`.
- **Resume lands on `qa`.** A run killed inside the QA handoff resumes at `state="qa"`,
  `flow="Coder"`, carrying `epic` and both counters, and the resumed run does not re-enter `dev`.
- **The nested drain keeps its own story record.** `prepare_fix_story` exists because the nested
  drain runs in the *parent's* run scope, where a second `prepare_story` call would overwrite the
  record `commit` reads to know which story it is committing. Both records survive side by side
  (`STORY-1` and the drained slug), the bullet leaves `docs/backlog.md`, and one commit covers the
  story and the fix — which is the whole reason the drain is nested here rather than handed off to
  `Fix`.
- **A static check now covers what no test could see.** `tests/test_prompts_exist.py` walks the AST
  of all four workflow packages, finds every `self.agent(...)` prompt argument, and stats the file:
  **77 sites, all present**. This is the check stage C3's finding asked for, and it is
  cross-workflow rather than `coder`-only because the hole it closes was never `coder`-specific.
- **One widening, stated.** `setup()` calls `resolve_workspace_dirs` for every mode, where the YAML
  resolved the workspace only on the epic path. It is idempotent and read-only, and it is what makes
  story mode's `docs_path` resolution identical to epic mode's; recorded because this loop widens
  nothing without saying so.
- **Not demonstrated:** any of the five sub-flows *inside* the main graph on real nodes — that is
  what their own suites do, and the composition of the two is the gap this file leaves; a run
  against a real GitHub PR, seamed here as everywhere in this port; and `dream`, which is entered by
  no state in the main graph and only through its own console script.

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
- **`commit-multi-repo.py` and `branch-multi-repo.py` are referenced by no graph, and were already
  dead before this port.** Grepping the whole tree turns up exactly two references each — a test
  (`base-library/workflows/coder/tests/test_multi_repo_git.py`) and a doc (`docs/multi-repo.md`) —
  and no workflow node. `commit-story.py` and `branch-story.py` do the multi-repo work the names
  suggest. They are not ports; they are deletion-list entries, along with their test and the doc's
  claim.
- **`open-multi-repo-pr.py` is the third graph-unreferenced multi-repo script.** Same shape as the
  two above: one reference in the whole tree (`coder/docs/multi-repo.md:205`) and no workflow node.
  `open-story-pr.py` does the per-repo PR fan-out the name suggests, and it is the one the graph
  actually wires. Deletion-list entry, with the doc's claim about it.
- **`open-story-pr.py`'s `base_branch` argument reaches nothing.** The script read it, coerced it
  (`base = base or "main"`), and then never passed it anywhere — every PR's base comes from
  `get_repo_base_branch`, whose own fallback is a separate literal `"main"`. So a run configured
  with a non-`main` base opened its story PRs against whatever each repo declared or probed to,
  never against the configured value. The port keeps the parameter, inert, because wiring it
  through would change behavior; loop 2 should decide whether the fix is to wire it as the fallback
  or to drop the argument from the graph.
- **`fresh_import` is gone, and one behavior goes with it.** Both status-stamping scripts reached
  `story_status.py` through `scriptutil.fresh_import("story_status", also_purge=("ostler",))`, a
  re-import per call so that a mid-run edit to ostler — an environment-fix loop landing a change
  while QA nodes are still ahead in the graph — was not shadowed by the copy an earlier node had
  cached in `sys.modules`. That only worked because each node was a separate script *import*; under
  the driver every node in a run shares one interpreter and one import, so the port is a plain
  module-scope import and the mid-run-reload behavior is genuinely lost. Recorded rather than
  absorbed: it is the only thing in `coder` that `fresh_import` bought, and loop 2 should decide
  whether an in-run ostler upgrade is a case worth re-supporting or one worth declaring out of
  scope.
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
- **The standalone `fix` flow implements only the first service layer.** `implement_fix.next` is
  `check_fix`, where `flows.dev`'s equivalent loops back to its layer selector. A drained fix whose
  plan dispatches two services gets one of them implemented and is then QA'd as a whole — and QA
  has exactly one retry behind it, so the second service's absence is most likely flagged as a QA
  failure rather than as an unimplemented layer. Ported as wired and pinned by
  `test_only_the_first_service_layer_is_implemented`; it reads much more like an omission than a
  decision, and adding the loop is a behavior change, so loop 2 should decide.
- **The fix drain prunes before it documents, so a documentation failure loses the item.**
  `prune_fix_item.next` is `document_fix_item`, and `document_fix_item`'s failure arm is a
  `type: fail`. A run that dies documenting has already removed the bullet from the backlog while
  leaving the work uncommitted, so the next run does not re-draw it — the item is silently gone
  from the worklist with its change sitting in the working tree. Preserved and pinned by
  `test_documentation_that_cannot_converge_fails_the_run_before_the_commit`. Moving the prune
  after the commit would fix it and is a behavior change.
- **`branch_fix_code_repos` is passed one argument where `dev`'s equivalent is passed three.** The
  YAML node lists only `spec_dir`, so `branch` and `docs_path` take their defaults and a blank
  branch falls back to the docs repo's *current* branch — the standalone drain never creates a fix
  branch. That happens to be coherent with the flow's own "one commit per item onto the current
  branch, no push, no PR" design, which is why it is preserved and asserted rather than
  harmonised; but it is one argument list away from the story flow's, and loop 2 should confirm
  the coherence is intended rather than lucky.
- **`plan_fix` has no `stamp_specs` after it, where `dev`'s plan turn does.** A drained fix's plan
  files are never registered as OKF Concepts, so the book has no record of what the fix planned to
  change. Same class as the `stamp_specs`-never-re-runs finding above, and the same cheap fix
  (`stamp_specs` is idempotent).
- **Cutting an epic branch dirties the queue file by one byte, and that byte hides the churn
  guard.** `branch-epic.py`'s reconcile — `content = show_file(root, base, QUEUE_PATH)` then
  `write_text(content)` — round-trips `docs/epics/index.md` through `git show`, which strips the
  file's trailing newline. So every epic branch starts with the queue file modified, and the
  **first** story of any epic always has something to commit whether or not it did any work. The
  zero-diff churn guard therefore needs *four* consecutive empty stories to trip on a fresh epic,
  not three. Inherited, not introduced: the port's `_reconcile_queue` is the YAML's three lines.
  Found by a test that expected three and got a pass; the test now uses four and says why. The fix
  is one `+ "\n"`, and it is a behavior change to the queue file's bytes, so it is loop 2's.
- **The epic CI gate is inert, on both engines.** `open_pr` emits `ci_epic` as the bare epic name,
  and every consumer then derives its own branch: `_open_epic_pr` and `merge-pr.py` build
  `feat/{epic}`, while `await-pr-checks.py:94` and `push-epic.py:46` assign `br = epic` and look
  for a PR on a branch that does not exist. The poll finds nothing, answers `unavailable`, and the
  whole CI cluster is a pass-through — which is why an offline test can walk it end to end and see
  `should_gate=True` with no gating. Preserved and asserted as `unavailable`; whether the fix is to
  emit the branch or to derive it in one place is loop 2's.
- **`zero_diff_count` is never seeded in the YAML.** `incr_zero_diff` reads a var no node
  initialises and no `vars:` block declares — it works only because the engine's context returns
  empty for an unknown key and the increment coerces it. The port makes it a state parameter with
  an explicit `0` default, which is the same behavior with the hole closed.
- **The nested drain in the main graph has the same three defects as the standalone `fix` flow,
  independently.** It implements only the first dispatched service layer, calls
  `branch_fix_code_repos` with one argument where `dev`'s equivalent gets three, and passes six
  arguments to `implement-plan.md` where `dev` passes nine. These are the same findings recorded
  above for `flows/fix.py`, seen a second time in a graph that was written separately — so the fix
  is one shared shape, not two patches.
- **`paths.OPERATOR_DIR` is now referenced by nothing.** It named `.agents/operator`, where the
  YAML's `await-operator.py` staged its context files; every gate in the port writes to
  `operator_context_path()` under the docs tree instead, which is where the YAML's own gates
  pointed. Kept, because deleting is loop 2's; a deletion-list entry, not a defect.

## Loop 2 — starting state

Loop 1.1's exit hands loop 2 a repo where **both engines work and one of them has no users left in
this tree.** Loop 2 is deletion, and this is the list, ordered so each step leaves the suite green.

**Before deleting anything, three things are true and worth re-checking rather than assuming:**
`make test && make check-public` passes; all four names resolve to packages (`workhorse run <name>`
prefers an installed package over a library layer, so the YAML copies are already shadowed for
anyone with the distribution installed); and no port has been run against a live agent — every
parity claim in this file is against real nodes with the agent turn scripted.

### 1. The deletion list

| What | Size | Note |
|---|---|---|
| ~~`base-library/workflows/{author,coder,okf-builder,research}/workflow.yaml`~~ | ~~7,719 lines~~ | **Done, step 2.** All 7,719 accounted for as states in a `workhorse_workflows` package |
| ~~…their `scripts/`~~ | ~~15,820 lines across 131 scripts~~ | **Done, step 2** — 127 by then, the four counters having gone with their graphs. One was carried out instead: `research/new_program.py` |
| ~~…their `tests/`~~ | ~~56 files~~ | **Done, step 1** — 63 files in the end, plus three `pytest.ini`. They had to go with the engine they ran on |
| ~~…their `prompts/`~~ | ~~—~~ | **Done, step 2, after the diff this row asked for.** 33 identical, 22 drifted by the node-key wrapper and the `CONSUMED` sentinel, 0 present in the base and missing from a port |
| ~~Both `await-operator.py`~~ | ~~555 lines~~ | **Done, step 2** — three copies, not two: `author/scripts/` (280), `author/surveyor/scripts/` (275) and `coder/scripts/await_operator.py` (323), 878 lines of ctypes inotify. They lived under `base-library/workflows/`, so list item 5 closed with list item 2 |
| ~~`init_counter.py` / `incr_counter.py`~~ | ~~—~~ | **Done, step 2.** Counters are state parameters now |
| ~~`commit-multi-repo.py`, `branch-multi-repo.py`, `open-multi-repo-pr.py`~~ | ~~—~~ | **Done, step 2**, along with `test_multi_repo_git.py` (step 1) and `coder/docs/multi-repo.md` |
| ~~`board.py`, `checkout-workspace.py`, `gh-token.py`~~ | ~~—~~ | **Done, step 2.** Unreferenced |
| ~~`graph/`, `runner/{script,branch,call}.py`, `main.py`'s engine half~~ | ~~~1,760 + graph~~ | **Done, step 1**, and *first* rather than last — the base-library test suites were the only thing pinning it, and they went in the same commit. `main.py` survives as the CLI |
| ~~`workhorse/workhorse/scriptutil.py`~~ | ~~154 lines~~ | **Wrong — do not delete.** ~20 modules under `workflows/src/workhorse_workflows/**` import it. `kit` replaced the *split-out* half, not the file |
| `paths.OPERATOR_DIR` | 1 line | Stranded by the port |

### 2. What the engine deletion is actually blocked on

`pyflow` is not free-standing today. It imports `workhorse.artifacts`, `config_run`, `rundir`,
`packaged` and `runner.agent` — all keepers — but also two things that go with the YAML engine:

- ~~`engine.py:29–30` imports `WorkflowContext` and `AgentNode`/`OutputSpec` from
  `workhorse.graph`.~~ **Cleared in loop 2 step 0.** They were never the YAML front-end's: the
  context bag is what a prompt renders against and `AgentNode`/`OutputSpec` are what a turn is
  described to `runner.agent` with — both front-ends build one. So they moved *out* of `graph/`
  (to `workhorse/context.py` and `workhorse/runner/spec.py`) rather than being copied into
  `pyflow`, and `graph/` now depends on them rather than the reverse.
- ~~`registry.py:180` calls `workhorse.main.main(...)` for the console script — the entire CLI
  (params, run ids, resume, `dot`, `config`) lives in the YAML engine's `main.py`. **This is the
  real work of loop 2**: the CLI has to be lifted out of `main.py` before `main.py` can go, and
  that is a refactor, not a deletion.~~ **Cleared in step 1, by not doing it.** The CLI does not
  have to move: `main.py` is not the YAML engine's, it is the CLI's, and the engine was the half
  that left. Nothing was renamed and nothing was repointed.

Also on the way: ~~`workhorse.testing.WorkflowRun` (575 lines) is the YAML whole-workflow harness and
`workhorse/tests/` is largely YAML-engine tests. They are the safety net for every step above, so
they are deleted *after* the thing they test, not before.~~ **Done in step 1**, in the same commit
rather than after it — a test whose subject is deleted is not a safety net, it is a red suite.

### 3. The behavior decisions this loop deferred

Every one is a "preserved and pinned, fixing it is a behavior change" from the findings above, and
none can be settled by a port. Grouped by what they cost to get wrong:

- **Silently loses work:** the fix drain prunes before it documents; the trailing-newline dirty
  queue; `stamp_specs` never re-running after a refine.
- **Silently does less than it says:** the inert epic CI gate; `open-story-pr.py`'s inert
  `base_branch`; the first-service-layer-only drain (twice); `fix_ci`'s lifetime attempt budget and
  its unreachable `ci_summary`; `verify-review-resolution.py`'s hardcoded spec path.
- **A knob that does nothing:** eight declared-but-inert `max_*` vars across four flows. The sweep
  is now unambiguous — every `max_*` in the YAML is suspect until read.
- **Unbounded:** the QA setup gate's operator cycle, which only terminates because the transition
  budget stops it.

### 4. The three engine-side items, which are not deletions

1. ~~**The context manifest never reaches a pyflow prompt**~~ — **done**, loop 2 step 0.1, on the
   user's call. It was the largest parity gap in this loop, and it landed *before* the YAML engine
   goes, while `main.py` was still there to copy the behavior from. See "Loop 2 — the deletion".
2. **`refuel:` has no counterpart, and as of step 1 there is no implementation left to read.** The
   YAML's progress-metered gas tank distinguished a productive long run from a spin; the driver's
   flat transition budget does not. A driver-side refuel is a design question, so step 1 deleted
   `_GasTank` rather than porting it — the shape is recoverable from `git show <step-1>^` if the
   answer is "yes". The otel instruments (`workhorse.gas`, `gas.capacity`, `gas.refuels`) were kept
   and are now inert, so a future refuel has somewhere to report to.
3. **A state that shadows a `dir(Workflow)` name is silently not a state.** It has bitten twice out
   of four workflows (`validate`, twice). A `__init_subclass__` check is a small driver change and
   the trap is a rate, not a coincidence.

### 5. Two structural moves, both cheap now and expensive later

- **The package layout** (`docs/backload.md`): group a workflow by *flow* — `coder/qa/{flow.py,
  nodes.py}` plus a `shared/` — rather than `nodes/`-by-subject plus `flows/`. It is a rename of
  every module in all four ports, so it wants to be one mechanical commit, and it wants to happen
  before anything else is built on the current layout.
- **Environment variables read inside nodes** (same file: "using environment variables in nodes and
  workflow IS PROHIBITED"). `coder`'s nodes read `AGENT_REPO_DIR`, `CODER_WORKSPACE` and
  `CODER_DOCS_PATH` exactly as the YAML scripts did. Converting them to inputs touches every port.

### 6. One sweep this loop could not do

**Every ported prompt's free variables against its call site.** A YAML prompt could read anything
in context; under `pyflow` the render context is the `args` dict alone, so only the values a port
*noticed* get passed. `implement-plan.md` was caught reading three (`story_path`, `spec_dir`,
`impl_instruction_paths`); the drain was caught passing six where nine were wanted. Nothing
proves the rest are complete — `tests/test_prompts_exist.py` checks that a prompt *file* exists,
which is a different question. A Jinja-AST sweep over every `prompts/**/*.md` against its
`self.agent(args=…)` is mechanical and belongs at the top of loop 2.

## What was next, and is now done

Both items this section carried through loop 1.1 are closed.

1. **Port `coder`** — landed across nine stages (A, B1, B2, C1, C2, C3, D1, D2, D3, D4), deleting
   nothing, in the whole package shape: `workflow.py` holding only the class, `nodes/` grouped by
   subject, schemas, `paths.py` for the derivations, `flows/` per sub-graph, both
   `workflows/pyproject.toml` lines, and tests under `workflows/tests/coder/` mirroring the node
   modules. 308 YAML nodes across nine graphs became 102 states, with 119 end-to-end tests.
2. **Record parity per workflow, here.** Done, in the fourteen `### Parity` sections above. Each is
   behavioral rather than asserted: real nodes against a temp git repo with only the agent turn
   scripted, artifacts read back off disk, resume driven through a real interruption. Where a
   behavior could not be reproduced offline — a live agent, a real GitHub PR, docker — the section
   says so under its own "Not demonstrated" heading rather than claiming coverage it does not have.

What is next is **loop 2**, whose starting state is the section above.

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

---

## Loop 3 — the documentation pass

Loop 3 changes no behavior. Where a doc could only be made true by changing code, that is
recorded here as a finding rather than fixed.

| Iteration | Commit | What |
|---|---|---|
| 1 | `96d6e31` | The three stale skills under `base-library/library/skills/stablemate/` |
| 2 | _this commit_ | `workhorse/docs/WORKFLOW.md` becomes the YAML→Python migration guide |

### Iteration 1 — the skills

`stablemate-workhorse-scripting` was **rewritten**, not edited: its spine was the "stdout
must be valid JSON matching `outputs:`" protocol, and a node returns a typed value. What
survived is `main(logger)` (the design chose that contract so scripts port as-is) and the
separation-of-concerns section, which is about workhorse being generic and is unaffected.
Its `applyTo` glob moved from `scripts/**/*.py` to
`**/workhorse_workflows/**/*.py, **/nodes/**/*.py, **/workflow.py`, because that is where
nodes live now. New sections cover the `@blueprint.node` contract, the port recipe from a
`main(logger)` script, `aliases`/`retries`/`stub` and the deliberate absence of `timeout=`,
idempotency-not-determinism, `WorkflowFailed` routing, `workhorse_workflows.kit`, and
substitution-based testing through `Registry.override` / `RunEnv`.

`stablemate-coder-workflow` was largely rewritten: `vars:` became the workflow-inputs
table, the node topology became the 27-state topology, `get_node_output()` became the
three tiers, and the standalone-flow section became `Registry.add_flows(...)`.

`stablemate-okf-modeling` needed two lines, not a rewrite — it models *documents*, and only
its examples named the retired schema.

**Checked before rewriting:** the two copies of each skill (`base-library/library/...` the
source, `.claude/skills/...` farrier's install) had **not** drifted. The whole diff was
render artifacts — `applyTo:` folded into the description, a `metadata:` block added,
`{% raw %}` stripped. Edit the source and re-install; there is nothing to reconcile.

**Findings from iteration 1:**

- `agents/workflows/coder/docs/repo-modes.md`, linked from the coder skill as the
  authority on mono-repo vs multi-repo, **does not exist anywhere in the tree** and has no
  successor. The only surviving statement of that contract is the module docstring of
  `workflows/src/workhorse_workflows/coder/paths.py`, which the skill now points at.
- `workhorse/otel.py` still defines `gas_level()` / `gas_refuel()`. pyflow has no gas tank
  and no `refuel:`; the instruments are dead and nothing writes them. Deleting them is a
  code change, so it stays a finding.

### Iteration 2 — the YAML schema reference

`workhorse/docs/WORKFLOW.md` (500 lines) was a schema reference for a schema that no longer
exists, carrying a banner that said its successor "has not been written yet". That stopped
being true: **`workhorse/docs/AUTHORING.md` is the successor**, split out of the 1111-line
README in `16e971e`, and it already documents `Workflow`/`Blueprint`, states as methods,
`Continue`/`Done`/`Await`/`WorkflowFailed`, `self.call`/`agent`/`handoff`/`output`,
`aliases=[…]`, the `(state, params)` checkpoint, the node index as the substitution seam,
and `labels()`. Nothing was reproduced from it.

So WORKFLOW.md was rewritten as the **migration guide** instead — the public obligation
owed to anyone still holding a `workflow.yaml`. It keeps its path (links to it do not
break), and it is a mapping table rather than a schema: top-level keys, node types, values
between nodes, the flow `vars` contract, invocation, checkpoints. It states what did *not*
change (prompt rendering and the Jinja context including `node_timeout_s`/`_min`, power
tiers, the resilience ladder and every `AGENT_*` knob, run artifacts, auto-resume,
`--dry-run` and `dot`) so a port touches the graph and nothing else.

Retargeted in the same commit, because they named WORKFLOW.md as the *current* engine API:
both scripting skills' opening pointer, `workhorse/docs/DEVELOPMENT.md`'s file map, and
AUTHORING.md's own blockquote about it. `workhorse/docs/GUARDRAILS.md` claimed the engine
narrative logs `agent →`, `script →`, `branch →`, `flow →`, `call →`; three of those node
types are deleted, and the driver actually logs `state →`, `call →`, `agent →`, `flow →`,
`await →`, `resume →`.

**Findings from iteration 2:**

- **`requires:`, OutputSpec `default:`, and per-node `activity:` have no Python
  counterpart.** All three are deliberate — dependencies are `[project.dependencies]` on an
  installed distribution, the resilience ladder nulls a `returns=` model's keys rather than
  guessing a value from a key's name, and activity is a flagged log record. The one with a
  behavioral edge worth naming: a YAML author could declare the *exact* value a defaulted
  node emitted (`default: {status: blocked}`) and route on it; a Python author cannot, so
  every branch driven by an agent reply needs a safe arm for the empty reply. Documented,
  not built.
- **`workhorse/workhorse/pyflow/__init__.py`'s module docstring showed
  `Continue(self.review, notes="")`** — a two-argument call to a three-argument transition,
  which raises `TypeError` if anyone pastes it. `Continue(result, next, /, *args,
  **kwargs)`. Corrected, along with the dangling `self.review` the example never defined.
  Docstring only; no behavior.

### Iteration 3 — the OKF book's index, format and driver pages

Work-order item 3, first half. The book's two **entry points** were the stale ones that
mattered most, because every other page is reached through them:

- **`docs/features/workhorse/workhorse.md`** — the `type: cli` index, titled "fail-soft
  runner for **YAML** agent workflows" and documenting `--workflow <path>`,
  `_resolve_workflow_path`, `_resolve_library_dir`/`WORKHORSE_LIBRARY_DIR`, `dot --pin`/
  `--leaf`, `load_workflow`, terminal/fail nodes, and a split `~/.config/workhorse/` vs
  `~/.config/farrier/` config. Rewritten from `main.py` and `pyflow/run.py`: name-only
  resolution through the `workhorse.workflows` entry-point group, the two front doors, the
  five subcommands as they actually parse, `config set-base` and the unified
  `~/.config/stablemate/config.toml`, exit codes 0/1/130. **It never appeared in `ostler
  doctor`** — its `code:` citation (`main.py::main`) still resolves, so nothing about the
  page's 281 lines of prose was checkable.
- **`docs/features/workhorse/workflow-format.md`** — carried a "this format no longer
  exists" banner over 164 lines of YAML schema. Its *subject* survives under a new name, so
  per the loop's stop rule it was rewritten rather than deleted: the workflow package is now
  the format, and the page documents package layout, `Registry`, the entry point, the
  console script, the `Workflow` subclass, states, transitions, `Blueprint`, nodes,
  `prompts/`, and a new `## The agent turn` section (`returns` / `power` / `timeout` /
  `cwd and add_dirs`).
- **`concepts/pyflow-driver.md`** and **`concepts/pyflow-state-graph.md`** were already
  grounded and correct, but framed as *one of two engines* — "the sibling of the YAML
  node-walk engine", "the analogue of the YAML engine's gas tank", a whole "Two engines, one
  runs directory" section. De-framed: one engine, with the retired one referred to in the
  past tense where it explains a choice.
- **`run-artifacts.md`** — the anchor `workhorse/README.md#sessions-per-node-clean-context`
  broke silently in the README split (`16e971e`); retargeted to
  `workhorse/docs/DEVELOPMENT.md#sessions-per-turn-clean-context`.

**Findings from iteration 3:**

- **`ostler doctor` grounds only `code:` bullets attached to a recognized OKF unit node.**
  `doctor.py::_check_code_grounding` iterates `graph.ui_nodes` and reads `node.meta["code"]`;
  a `- code:` bullet under a plain `` ## `name` — prose `` heading belongs to no unit, so it
  is never checked. Three pages dangle **unreported** because of this:
  `concepts/scriptutil.md` (8 dead symbols — `resolve_workspace`, `checkout_workspace`,
  `get_repo_config`, `build_dispatch_list`, `get_affected_repos`, `open_repo`, `run_gh`),
  `concepts/testing.md` (8 dead `WorkflowRun`/assert symbols), and
  `concepts/workflow.md::_step_loop`. This is the loop's *"if it cannot report this, say so
  instead of grepping around it"* case: said, not grepped around. Fixing it is an ostler
  change, so it stays a finding.
- **`main.py::_add_test_args` still helps `"Directory containing workflow.yaml and a tests/
  subdirectory"`** — a stale string in shipped code, printed by `workhorse test --help`. The
  directory it wants is a workflow *package*. Reported, not fixed (no behavior this loop).
- **`runner/spec.py`'s module docstring says "both front-ends build one … The YAML loader
  validates a node's mapping into it"** — present tense about a deleted loader.
  `pyflow/engine.py:305` is now the only builder of an `AgentNode`. Same for
  `pyflow/driver.py:65`, "The two engines share a runs directory". Reported, not fixed.
- **`args` rendering *did* change, and both WORKFLOW.md and AUTHORING.md said it did not.**
  The YAML `args:` was a dict of Jinja template **strings**, so an `int` or a `Path`
  stringified on the way past; `self.agent(args={…})` merges real Python objects into the
  render context (`pyflow/engine.py` passes `args={}` on the node and puts the values in the
  `WorkflowContext` instead, with the comment saying exactly why). Corrected in WORKFLOW.md's
  "what did not change" list and stated in the format page.
- **`self.agent(timeout=…)` defaults to 3600s, not unbounded** — `AgentNode.timeout` is
  `float | None = 3600` and `engine.py` only sets the key when the caller passed one. The
  first draft of the format page said "unbounded"; corrected against the source.

**`ostler doctor` went 18 → 29 errors, and that is the point.** Eleven of the new ones are
inbound links from stale `concepts/` pages into anchors the rewritten `workflow-format.md`
no longer has (`#outputspec`, `#script`, `#branch`, `#call`, `#vars`, `#flows`). The dangle
was always there — the old page kept it *hidden* by preserving retired anchors. Every one of
the 29 now names a page whose subject is deleted, plus six in `docs/features/farrier/`
(`install.py` lost `render_expected`, `resolve_library_dir`, `Renderer`, `main`,
`read_config` — outside this loop's scope but genuinely dangling). Live pages that merely
*linked* into the format page (`extract-outputs`, `render-prompt`, `run-agent`,
`stream-subprocess`, `flows/workhorse-choose-backend-and-power`) were retargeted in this
commit; their bodies still speak YAML and are the next iteration's work, along with the four
stale `flows/` walkthroughs.

**okf-builder was not launched**, deliberately. The builder grounds a page against symbols
that exist; it cannot decide that a page's *subject* was deleted, which is exactly what this
iteration had to decide. Secondarily, `829d848` is labelled "step 1" of an in-flight refactor
of `runner/agent.py` — the code path an unattended builder run drives hardest.

**Open question for the operator** (asked, not acted on, per the stop rule): nine
`concepts/` pages — `workflow.md`, `dot-renderer.md`, `load-workflow.md`, `run-script.md`,
`run-call.md`, `run-flow.md`, `evaluate-branch.md`, `builtins-registry.md`, `gas-tank.md` —
have subjects that survive *only* in the sense that `pyflow-driver.md` and
`pyflow-state-graph.md` already document what replaced them. Rewriting them duplicates those
two pages; deleting them with links redirected is the honest move, and deletion needs a call.

### Iteration 4 — the four `flows/` walkthroughs

Rewritten, not deleted: all four subjects survive under new mechanics, so the stop rule
applies. `docs/features/workhorse/flows/` —

- **`workhorse-setup-and-run.md`** — was "set up the prompt library and run a workflow",
  narrating `config set-library`, `<library_dir>/workflows/<name>/workflow.yaml`,
  `_resolve_library_dir`, `load_workflow`, `_step_loop` and `OutOfGasError`. Now: *install*
  a workflow distribution — there is **no configuration step**, because publishing the
  entry point is what makes the name resolvable — then `workhorse run <name>`, with the
  path-refusal rule, the eager `Registry.directory()` and the three exit codes (0 / 1 /
  130). Its two `verify:` citations named tests that no longer exist
  (`test_library_dir_from_workhorse_config`, `test_bare_name_resolves_against_library`) and
  were replaced with three that do.
- **`workhorse-author-test.md`** — was an API tour of `workhorse.testing`'s `WorkflowRun` /
  `mock_agent` / `mock_agent_sequence` / `mock_command` / `RunResult`, PATH shims under
  `.workhorse-test/bin/`, and `workhorse --workflow <path>` driven as a subprocess. **None
  of that exists.** Now: construct the `Workflow`, build a `RunEnv`, substitute through
  `Registry.override` / `run_agent=` / `stub_agents` / `@blueprint.node(stub=…)`, call
  `drive(wf, env)`, assert with the four helpers `testing.py` still has. `workhorse test`
  survives unchanged and is still the runner.
- **`workhorse-author-visualize-run.md`** — was `--pin`/`--leaf` on `dot --workflow <path>`.
  `dot` now takes a **name** and only `--name`/`--output`; there is no pinning and no leaf
  cutting. The rewrite makes the author's two checks explicit and different: `dot` +
  `preflight` read *every* path off the source, `--dry-run` walks *one* over stand-in
  values, including the "no declared `stub_agents` ⇒ a fail terminal still exits 0" rule.
- **`workhorse-crash-resume.md`** — was `write_checkpoint(current_id, context)`,
  `_should_fast_forward`, `done.json`/`context_after.json`, `resume_interrupted_node`.
  **The whole fast-forward half is gone**: pyflow re-enters the checkpointed state from the
  top, so the contract is *idempotency, not determinism* — which the page now says outright,
  along with `auto_resolve`'s stable dir, the `p<sha1[:8]>` run id, the non-pyflow
  checkpoint refusal, `aliases=[…]`, and the original-start anchoring of
  `WORKHORSE_MAX_RUNTIME_S`.

`ostler doctor`: **30 → 27**. The three cleared are the tree's only two
`unresolved-relation` errors (`workhorse-author-visualize-run.md`'s `steps:` targets
`#node-types` and `#flows`) plus the `#sample-load-valid` missing anchor. `flows/` is now
clean; every remaining error is in `concepts/` or `docs/features/farrier/`. (30, not 29:
the concurrent workstream renamed `_opencode_on_event` between iterations.)

**Learned, and worth not re-discovering:** a link inside a flow's `steps:` bullet is parsed
as an OKF **relation** and must resolve inside the book — a repo-relative link to
`workhorse/docs/AUTHORING.md` there is an `unresolved-relation`, and the same link in the
page's prose is fine.

#### Findings — code the docs cannot describe truthfully (no code changed)

1. **`workhorse/workhorse/testing.py`'s module docstring example does not run.** It imports
   `drive` and `stub_nodes` from `workhorse.pyflow`, which exports neither; `drive` is
   `pyflow.driver.drive(wf, env, resume=None)` and is called there without its required
   `env`; `stub_nodes` is `pyflow.engine.stub_nodes(index) -> index`, a pure function, used
   there as a context manager. Deferred to item 4 ("every runnable example"), where it
   belongs.
2. **`pyflow/run.py:139` prints an invalid resume hint** —
   `workhorse --resume-run <dir>`, which exits with "workflow is required". The working
   form is `workhorse run <name> --resume-run <dir>`.
3. **Three module docstrings still speak of the YAML engine in the present tense**:
   `pyflow/run.py`, `pyflow/driver.py:65` ("The two engines share a runs directory"), and
   `runner/spec.py`.
4. **`main.py:341`** — `workhorse test`'s help still reads "Directory containing
   workflow.yaml and a tests/ subdirectory".
5. **`artifacts.py` has four production-dead methods** — `write_checkpoint`, `write_branch`,
   `read_done`, `read_context_after`. Only `tests/test_idempotency.py` and
   `tests/test_otel.py` call them, which means `test_idempotency.py` tests a fast-forward
   mechanism **no engine uses**. Correspondingly, `concepts/artifact-writer.md` documents
   all four and does **not** document `write_state_checkpoint`, the one pyflow actually
   calls — a live page describing a dead API, which `ostler` cannot see because both
   symbols exist.
6. **`config set-library` / `set-stablemate` still exist** and still write `library_dir` /
   `stablemate_dir`, but `library_dir` no longer participates in workflow resolution. The
   command persists a key nothing reads.

### Iteration 5 — the three surviving-subject artifact/config pages

Rewritten, not deleted — all three subjects survive:

- **`concepts/artifact-writer.md`** — was a tour of the YAML engine's writer API and did not
  mention `write_state_checkpoint`, the one method pyflow actually calls (finding 5 of
  iteration 4). Now grounded on the file as it stands: the constructors (`__init__`,
  `resume`, `at`, `subscope`), the live writes (`write_state_checkpoint`, `record_node`,
  `write_step`, `record_interrupt`, `finish`, `write_final_context`), the live reads
  (`read_checkpoint`, `read_output`, `read_events`), and a closing
  **"Retired with the YAML engine"** section that keeps `write_checkpoint`, `write_branch`,
  `read_done` and `read_context_after` documented **under their original headings** — so
  inbound anchors still resolve — while saying plainly that no production caller remains.
  Three behaviours the source makes true and the old page did not say: `handoff` calls
  `subscope` **without** `resume=`, so a child scope always starts clean (justified: pyflow
  checkpoints the *parent* state); `write_step` is always passed `context_after={}` and
  `next_node=None`, so those two files are constant under pyflow; `_write_run_json` now
  records `pid`.
- **`run-artifacts.md`** — the layout page. `checkpoint.json`'s fields were the YAML
  engine's (`current_id`, `context`, and the fast-forward `seq` rule) and are now pyflow's
  (`engine`, `flow`, `state`, `params`, `waiting_on`, `inputs`, `ctx`, `seq`,
  `updated_at`); `branch.json` is retired; `context_after.json` is documented as **always
  `{}`**; `done.json`'s `next` as **always `null`** (no node graph, so no edge to name);
  `prompt.md` as the rendered agent prompt / `name(args)` call description /
  `handoff → <ChildClass>`; `_flow/` as always entered fresh. All six inbound anchors were
  preserved.
- **`concepts/config.md`** — its `code:` target `workhorse/workhorse/config.py` no longer
  exists; the module is `core/stablemate_core/config.py`, one file shared by workhorse and
  farrier. Re-grounded, and the six inbound anchors kept. Added what the page never
  documented: `check_config_version`/`ConfigVersionError`/`CONFIG_VERSION` and why the
  version guard lives on the **file** (two pipx venvs each carry their own copy of the
  module), `legacy_config_paths` and the legacy-merge fallback, `resolve_harness_env`, the
  `read_config` alias and the `write_*_dir` helpers, and the `$STABLEMATE_CONFIG` →
  `$WORKHORSE_CONFIG` → platform-default resolution order.
- **`flows/workhorse-choose-backend-and-power.md`** — one stale claim corrected in passing:
  `write_config_key` no longer "would corrupt a hand-written `[table]` section". It
  serialises with `tomli_w`, so nested tables survive; what it lacks is a *path syntax* for
  reaching into one. The page also still pointed at `concepts/workflow.md#execution` and
  `$WORKHORSE_CONFIG`, both re-pointed.

`ostler doctor`: **27 → 26**, the one cleared being `config.md`'s `dangling-code-ref`.
Every remaining error is in a `concepts/` page whose subject is gone (iteration 6 deletes
them) or in `docs/features/farrier/`.

**Learned:** ostler's `anchor_of` is *not* GitHub's slugger for headings containing `*` —
it collapses the run of punctuation, so `write_state_checkpoint(state, params, *, inputs,
…)` anchors as `…state-params-inputs-…`, with one hyphen where GitHub emits two. Compute
the anchor with `ostler.model.anchor_of` rather than by hand.

#### Findings — code the docs cannot describe truthfully (no code changed)

7. **`otel.py` still exposes gas instruments with no producer.** `gas_level(gas, capacity)`
   (`otel.py:214`), `gas_refuel(node_id)` (`:218`) and the `workhorse.gas` /
   `workhorse.gas.capacity` / `workhorse.gas.refuels` instruments (`:458`–`:465`) survived
   the deletion of `_GasTank`. Nothing calls them; the metrics can only ever be empty.
8. **`pyflow/workflow.py:310` cites a mechanism that no longer exists** — the comment reads
   "The gas tank already bounds node work".
9. **`run-artifacts.md`'s runs-dir default was wrong, and had been for longer than this
   loop**: it claimed `<workflow-dir>/runs`; `main.py:298` is
   `(Path.cwd() / ".agents" / "runs").resolve()`. Corrected in the rewrite.
10. **Two `verify:` targets named test files that no longer exist** —
    `run-artifacts.md` cited `tests/test_call_node.py::test_call_node_end_to_end` and
    `tests/test_flows.py::test_resume_across_flow_boundary`. `ostler` does not check
    `verify:` targets the way it checks `code:` targets, so both were invisible. Replaced
    with three live `test_pyflow.py` tests plus the surviving
    `test_idempotency.py::test_checkpoint_seq_increments`.
11. **`sessions.jsonl` was an entirely undocumented run artifact.** `runner/agent.py:487`
    appends `{"node", "session_id"}` beside `.session_id` after every successful turn — the
    only durable way to map a *past* node back to its session transcript. Now documented.
12. **Two more `missing-code-symbol` errors are the concurrent workstream's, not the
    port's**: `code-workspace-file.md` → `scriptutil.py::_read_workspace_file` and
    `concepts/opencode-on-event.md` → `runner/backends.py::_opencode_on_event`. Both are
    renames in files loop 3 is not touching.

### Iteration 6 — retiring the graph-engine `concepts/` pages

Nine `concepts/` pages documented symbols the port deleted outright, so they were removed
rather than rewritten — `load-workflow.md`, `evaluate-branch.md`, `run-call.md`,
`run-script.md`, `run-flow.md`, `gas-tank.md`, `builtins-registry.md`, `dot-renderer.md`,
`workflow.md`. The loop's STOP rule covers "a doc whose subject survives under a new name";
none of these has one. `graph/loader.py`, `runner/branch.py`, `runner/call.py`,
`runner/script.py`, `main.py::_run_flow`, `main.py::_GasTank`, `builtins.py::REGISTRY` and
`graph/nodes.py::Graph` are gone with no successor, and the two arguable cases already have
complete replacements in the book: `dot-renderer.md` → `pyflow-state-graph.md#rendering`,
`workflow.md` → `pyflow-driver.md`.

Five surviving pages pointed into them and were re-pointed at what is actually true now:

- `run-agent.md` — "`[workflow execution](workflow.md#execution)` calls it once per `agent`
  node" → `drive` reaches it once per agent *turn*; the `workflow.md#resilience-fail-soft`
  back-reference is dropped, since this page is the authoritative spec and nothing else
  documents the ladder any more.
- `render-prompt.md` — `ResilientUndefined`'s "inconsistent with workhorse's fail-soft
  posture" now links to `run-agent.md`.
- `agent-backend.md` — "the `[workflow](workflow.md)` execution loop calls it per `agent`
  node" → `run_agent` drives it once per agent turn.
- `context-manifest.md` — `concepts/workflow.md` → `workflow-format.md`.
- `scriptutil.md` — the two `../workflow-format.md#script` links (a node type that no longer
  exists) → `#node`, and "before the graph starts" → "before the run starts". The rest of
  that page is still a later iteration's work.

`concepts/workflow-context.md` was **rewritten**, not patched: its subject survives
(`workhorse/workhorse/context.py::WorkflowContext` is still constructed by
`pyflow/engine.py`'s `self.agent`), but three of its four link targets were deleted pages and
most of its body described the graph walk. See findings 13–15.

`ostler doctor`: **45 → 27 errors, 0 warnings.** (It read 45 rather than iteration 5's 26
because `e68067f` — the concurrent workstream — landed between the two runs and split
`runner/backends.py` into a package, breaking 12 `code:` refs at a stroke.) **Every one of
the 27 remaining errors is a `code:` target the concurrent workstream moved, or a
pre-existing farrier one — none is the port's.** Catalogue: 12 × `runner/backends.py::…`
(the `e68067f` split), 5 × `runner/agent.py::_…` (symbols that moved with it), 6 × farrier's
`install.py` (pre-existing, unrelated to this loop), 1 × `scriptutil.py::_read_workspace_file`,
and `farrier.md#version` counted twice. Re-grounding the backend/agent pages on the new
`runner/backends/` port package is the next iteration's work, not this one's.

**Findings 13–15 (this loop changes no behavior; these are reported, not fixed):**

13. **`WorkflowContext.merge`, `get_dotpath` and `has_dotpath` have no caller left in
    workhorse.** Their callers were the graph walk (folding a node's `outputs:` into the
    running context) and `runner/branch.py::evaluate`'s unresolvable-path guardrail. Only
    `as_dict()` — read once by `runner/agent.py:679` — is live. The class is now a one-way
    render bag: built by `pyflow/engine.py` from `{manifest, args}`, unwrapped immediately.
14. **The name `WorkflowContext` now collides misleadingly with pyflow's `self.ctx`**, which
    is an unrelated thing (the object a workflow's `setup()` returned, restored from the
    checkpoint on resume). Under the YAML engine they were the same idea. The page now says
    so explicitly, because the docs cannot rename the class.
15. **`workflow-context.md`'s `verify:` pointed at `tests/test_branch_guardrail.py`, a file
    that no longer exists** — the same class of miss as finding 10, and the same cause:
    `ostler` does not check `verify:` targets. Repointed at
    `test_agent_recovery.py::test_rendered_prompt_is_written_and_only_path_is_printed`.
    Worth noting that two of three `verify:` misses found so far were only found by hand.

### Iteration 7 — the quick start, which did not exist

Work-order item 4 opens with a requirement the repo did not meet: *"the quick-start example
must EXIST and RUN"*. Every quick start in the tree pointed either at `author`/`coder` —
which want a repository, a manifest, an agent CLI and a private overlay — or at an
illustrative `acme` snippet with no prompt file behind it. A reader could not run anything.

**Shipped: `hello-world`**, a fifth workflow whose only job is to be the first one someone
runs and the file they copy.

- `workflows/src/workhorse_workflows/hello_world/` — `workflow.py` (~60 lines carrying one
  of each construct: a node, two states, an agent turn, a registry), `prompts/greet.md`,
  and an `__init__.py` saying why it exists and that nothing else in the tree imports it.
- `workflows/pyproject.toml` — the `workhorse.workflows` entry point and the
  `workhorse-hello-world` console script, both listed **first** in their group.
- `workflows/tests/test_hello_world.py` — three tests, because the three properties fail
  independently: the entry point resolves, `--dry-run` walks the machine green, and a real
  turn reaches `Done`. `test_prompts_exist.py` now sweeps it too (78 passing).

Verified by hand before being written into any doc: `workhorse run hello-world --dry-run`,
the same with `--params '{"name": "globex"}'`, the console script
`workhorse-hello-world run --dry-run`, and `workhorse dot hello-world`. `.agents/runs/` is
git-ignored, so the demo leaves no tracked residue.

Docs wired to it: `README.md` (install snippet, package table, a new **Your first run**
section with the real console output), `workhorse/docs/AUTHORING.md` (its opener now names
something runnable, and "A worked example" says it is illustrative), and
`workhorse/docs/WORKFLOW.md` (the "minimal port" Python snippet is a *translation*, not a
runnable file — it now says so and points at the real package).

Also corrected: `docs/features/workhorse/context-manifest.md:108` said "**Both engines load
it**" in the present tense. Its line 38 already claimed a manifest-free `hello-world` run
was possible — a forward-looking claim when written, and **true as of this commit**.

**Findings 16–18 (reported, not fixed — this loop changes no behavior):**

16. **`workhorse/entrypoint.sh:136` still runs `--workflow "${WORKFLOW_PATH:-/workflow/workflow.yaml}"`.**
    Unlike the prose findings, this is an executable file that cannot work: the flag was
    removed with the YAML front end. Every Docker path through that script is broken. Fixing
    it is a code change, so it is recorded here rather than made.
17. **`docs/features/workhorse/flows/coder-documentation-gate.md:40` carries
    `code: base-library/workflows/coder/workflow.yaml`** — a dangling reference to a deleted
    file that **`ostler doctor` does not report**. Same root cause as findings 10 and 15:
    ostler checks `code:` targets that resolve to a repo-relative path it knows how to walk,
    and silently passes ones it cannot. Three of the misses this loop found were found by
    hand, which is worth weighing before trusting a clean `doctor` as coverage.
18. **A node's `stub=` is load-bearing, and nothing says so.** `pyflow/engine.py::_blank`
    builds a dry-run stand-in with `returns.model_construct()`; for a model with required
    fields that yields an instance with *no* fields set, so attribute access raises
    `AttributeError`. A node whose result a later state **reads** therefore must declare
    `stub=` or `--dry-run` cannot pass — which is not what "dry run" suggests, and is how
    the first `hello-world` draft failed. Documented in the example's own comment; whether
    the engine should instead default required fields is a loop-2 question.

**Deferred, and now blocked on someone else's commit:** the concurrent workstream deleted
`workhorse/workhorse/runner/agent.py` mid-iteration and split it into `caps.py`,
`extract.py`, `failure.py`, `ladder.py`, `process.py` and `reframe.py`. Every `concepts/`
page grounded on `runner/agent.py::…` — roughly twenty, plus `classify-turn.md` and
`stream-subprocess.md` — is dangling as a result, and the old→new symbol map is not stable
enough to re-ground against until that lands.

### Iteration 8 — the cold walk, actually walked

Work-order item 5 opens with *"walk it yourself on a clean checkout and fix what you hit."*
So this iteration walked it literally rather than by reading: a `--no-local` clone of the
tracked tree at `89d18d5` into a scratch directory, `make sync`, and every documented
command run against **an empty `$HOME`/`$XDG_CONFIG_HOME`/`$XDG_CACHE_HOME`** so no
configured overlay on this machine could shadow the result.

**The headline: the cold path holds.** With no overlay, no config and no cache,
`make sync` succeeds and `workhorse run hello-world --dry-run` exits 0. With an agent CLI
present, `workhorse run hello-world --params '{"name": "globex"}'` also completes for real
— a live `claude` turn returning a validated `Greeting` in ~11s — and `workhorse dot
hello-world` renders. The claim that this path assumes a private overlay is **no longer
true as of iteration 7**; it was true when the work order was written.

**Then the harder half of the end condition — "write a new workflow from the docs alone" —
was tested by doing it.** A separate `acme-workflows` distribution was built outside the
checkout, installed with `uv pip install`, and `workhorse run greeter --dry-run` found and
ran it. It works, but three things needed for it appear **nowhere a reader would look**:

- **No `pyproject.toml` is shown anywhere.** README said "add it to your own distribution's
  `workhorse.workflows` entry points" and stopped. The only worked example is
  `workflows/pyproject.toml`, which is ~100 lines and carries `[tool.uv.sources] … workspace
  = true` — copying it *outside* this workspace does not resolve.
- **The entry point must name the `Registry` object, not `main`.** Pointing it at the
  console-script callable fails at resolution.
- **The install must land in workhorse's own interpreter**, and no command for a reader's
  own package was written down.

Fixed by a new **"Shipping your own, outside this repo"** section in
`workhorse/docs/AUTHORING.md` carrying the complete minimal `pyproject.toml` and the one
install command — verbatim the one that was just run green — with the README's last-mile
sentence pointing at it.

**Corrections to iteration 7's own claims, found by running them:**

- The README's expected output **omitted the `[workhorse] starting …` banner**, which a
  reader sees first on a terminal. (It landed mid-block in the capture only because the
  banner is `print()` on stdout while the narrative is logging on stderr, and a pipe
  buffers them differently than a tty does.) Added.
- "Those four lines" counted six. Reworded to name the four `state`/`call`/`agent` lines.
- The `ls` sample listed four entries; a run dir has six (`context.json` and `run.json` too).
- **`cat …/greet/prompt.md` under `--dry-run` shows `(dry-run) prompts/greet.md`, not a
  rendered prompt** — the dry run never renders one. The README invited a reader to look at
  a rendered prompt that is not there. Prompt inspection moved to the real run, where it is
  genuinely rendered with `{{ name }}`/`{{ letters }}` filled in, and the dry-run stub is
  now stated rather than glossed.

**Finding 19 (reported, not fixed):** the run-directory *name* differs between the two
paths — `hello-world-dry-run` is fixed and reused, while a real run gets
`hello-world-<id>`. That is `run_pyflow` forcing `run_id="dry-run"` under `--dry-run`, and
it means consecutive dry runs overwrite each other's artifacts. Fine for a quick start,
worth knowing before anyone treats a dry-run artifact directory as durable.

### Iteration 9 — the link sweep, and what `ostler` will and will not tell you

Work-order item 5: *"Check the cross-repo links (`workhorse/README.md` points at
`github.com/... blob/main` paths); files moved in loop 2, and those break silently."*

**That specific worry is not true.** Every
`https://github.com/GabrielCpp/stablemate/blob|tree/main/...` link in the tree resolves —
path *and* anchor — including the three deep ones into `workhorse/docs/AUTHORING.md`
(`#the-node-index-is-the-substitution-seam`, `#checkpoints-and-renaming`) and
`BACKENDS.md#initial-setup`. Loop 2 moved code, not the docs those links point at.

**The real breakage was two other classes, 58 broken links across 313 tracked Markdown
files, now zero.**

- **50 anchors with a collapsed hyphen run.** GitHub's slugger lowercases, strips
  `[^\w\s-]`, then replaces **each** space with a hyphen **without collapsing runs**. So a
  heading `## X — Y` slugs to `x--y`, with a *double* hyphen, because the em-dash is
  removed and both surrounding spaces survive as separate hyphens. Fifty links in
  `docs/features/workhorse/**` wrote the single-hyphen form and silently landed at the top
  of the page instead of the section. Repaired in `code-workspace-file.md` (14),
  `concepts/scriptutil.md` (17), `concepts/testing.md` (7), `concepts/artifact-writer.md`
  (4), `run-artifacts.md` (2), `concepts/render-prompt.md` (2), and one each in
  `concepts/codex-on-event.md`, `copilot-on-event.md`, `opencode-on-event.md`,
  `stream-jsonl.md`.
- **8 wrong-target paths**, seven of them wrong-depth `../` from `docs/plans/**` (which is
  two levels down, not one) — `okf-runbook.md`, `ostler-qa-verification.md`,
  `saddlebag-environment-pool.md`, `okf-ui-profile.md`, `workhorse-otel.md` (×2), and
  `ostler/docs/QA-RUN.md` pointing into a `docs/` that no longer holds that file. The
  eighth was not a depth error: `workhorse-otel.md` linked `groom/operator-inbox.md`, which
  **exists nowhere in the tree** — re-pointed at
  `docs/features/groom/flows/operator-answers-blocked-gate.md`, the surviving page that
  documents the answer write-back.

**Finding 20 — `ostler` cannot report this class, and the work order asked to be told.**
It says *"use `ostler` to find what dangles … and if it cannot report this, say so instead
of grepping around it."* `ostler doctor` checks **`code:` target integrity only**. It does
not check `verify:` targets, and it does not look at Markdown link targets or anchors at
all. So none of the 58 above were visible to it, and a purpose-built checker was used
instead. That checker was deliberately **not** added to the tree — it is unasked-for
tooling — but without one this fix will rot silently again, and a repeatable gate is worth
a decision.

**Finding 21 — what `ostler doctor` *does* report is exactly item 3's remaining work.**
39 errors, 0 warnings: **31 `dangling-code-ref`**, every one a
`workhorse/workhorse/runner/agent.py::…` or `runner/backends.py::…` citation in
`docs/features/workhorse/concepts/` left dangling by the concurrent split (`c284e0a`), plus
**8 `missing-code-symbol`** (6 in `docs/features/farrier/**` against
`farrier/farrier/install.py`, 1 at `workhorse/workhorse/scriptutil.py::_read_workspace_file`).
That enumerates the backend re-grounding item 3 deferred, so it no longer needs scoping.

**Finding 22 — the skills have not drifted.** Item 1 said to check whether
`.claude/skills/**` and `base-library/library/skills/stablemate/**` had diverged and to
*say so* rather than hand-edit both. All nine pairs differ, and the difference is **only
farrier's injected `metadata:` frontmatter** (`generated_by`, `source`, `resolve`,
`do_not_edit`) — 5–8 lines per file. Zero content drift; the installed copy faithfully
mirrors the source.

### Iteration 10 — the motivation, which was missing rather than duplicated

Work-order item 5: *"Motivate the design ONCE, in one place, and link to it. Five READMEs
each re-arguing why workflows are Python is how a repo reads as unfinished."*

**Finding 23 — the premise is inverted, and that is the more serious defect.** Nothing in
the tree argues why a workflow is Python. Six tracked files *assert* it —
`workhorse/README.md` (three times), `workhorse/docs/AUTHORING.md`,
`base-library/README.md`, `docs/features/workhorse/workflow-format.md`,
`flows/workhorse-setup-and-run.md`, the root `CLAUDE.md` — each stating the fact because
it needs it locally, and **none giving a reason**. A repo does not read as unfinished
because it argues a decision five times; it reads as arbitrary because it announces one
five times and defends it never. The rationale existed only inside
`workflow-as-python-state-machine.md` — the ~1,550-line plan that item 6 is about to
retire, which would have deleted the only written justification for the change the whole
loop is documenting.

Written once now, as **"Why a workflow is Python and not a config file"** in
`workhorse/README.md` — chosen because it is the PyPI landing page, so it is where someone
*evaluating* workhorse arrives, and because that file already carries the only `## Why`
section in the tree. Recovered from the plan's `## Why change anything` (lines 34–61) and
`## The trilemma this resolves` (683–698), which is the sanctioned narrow read: intent the
shipped source cannot express. It carries the three real arguments — values and loops are
what a graph schema cannot model (the constant kept in sync by comment, `for _ in range(3)`
emulated with four nodes and three scripts, every inter-node value a Jinja string);
dependency isolation, which the plan itself calls the bigger win; and the pick-two the
state boundary resolves, **including what it gives up** (a complete static graph — the
interior of a state is opaque to `workhorse dot`).

The five assertion sites now link to it rather than each implying its own reason: the root
`README.md`, `workhorse/docs/AUTHORING.md`, `workhorse/docs/WORKFLOW.md`,
`base-library/README.md` and `docs/features/workhorse/workflow-format.md`.

**Finding 24 — the migration note existed but was unreachable from the one page that
matters.** Item 5's last bullet calls a migration note "a public obligation". Iteration 2
already wrote it (`workhorse/docs/WORKFLOW.md`), and it was linked from the root README,
AUTHORING.md, workflow-format.md and DEVELOPMENT.md. But `workhorse/README.md` — the PyPI
page, the *most likely arrival point for someone holding a `workflow.yaml`*, since they
have the distribution and not the checkout — **never mentioned the YAML front-end at all**,
in any of its 450 lines. The obligation was discharged everywhere except where it was owed.
Fixed with a callout at the end of the new section.

Both remaining item-5 bullets are now done; item 5 is closed.

### Iteration 11 — item 4's `--workflow` sweep, which was one page and two un-ported files

The work order named eight files carrying `workhorse --workflow ./wf/workflow.yaml`. Read
against the shipped code, most of that list was already discharged: `base-library/workflows/`
**does not exist** (the named README is moot), and `saddlebag/README.md`,
`workhorse/docs/GUARDRAILS.md`, `workhorse/CLAUDE.md` and `farrier/docs/LAYOUT.md` were
already clean — LAYOUT.md's line 203 mention is a deliberate past-tense sentence about what a
library *used to* ship, and was left alone. The same goes for the two
`stablemate-workhorse-scripting` copies, `workflow-format.md:21`,
`flows/workhorse-setup-and-run.md:13`, the `workflows/src/**` port-provenance docstrings, and
all of `docs/features/workhorse/workhorse.md`, where `--workflow <name>` is the **current**
flag taking a name.

What was actually left was one page whose whole subject had died, one un-ported deployment
path, and two comments.

- **`docs/features/workhorse/concepts/testing.md` — rewritten, not deleted.** It was not
  three stale `--workflow` lines; the module it documents was replaced wholesale. It
  described `WorkflowRun(workflow: str | Path, sandbox: Path)` where "`workflow` is the
  `workflow.yaml` path", `mock_agent`, `mock_agent_sequence`, `mock_command`, `run()`,
  `RunResult` and its eight methods, two PATH-shim script templates, and three assertion
  helpers built on `RunResult`. **The shipped `workhorse/workhorse/testing.py` is 103 lines
  and exports four functions**: `make_git_repo`, `assert_file`, `assert_file_contains`,
  `assert_json_file`. The subject survives under a changed shape, so per the STOP rule this
  was a rewrite. The new page says what the module is *for* now — the two jobs a callable
  flow cannot do for itself — documents the four functions against their actual behaviour
  (the explicit `-b main`, the repo-local identity for identity-less CI, the
  README-only-if-absent rule, dict-subset vs list-exact matching), and carries a was→is table
  mapping every deleted symbol to what replaced it, so a reader arriving from an old test
  knows where to go rather than concluding the capability was dropped.
- **`workhorse/docs/DOCKER.md` — made honest rather than made true.** `WORKFLOW_DIR` "must
  point at a directory containing a `workflow.yaml`" is false, and it cannot be fixed here:
  `entrypoint.sh:136` still runs `workhorse --workflow "${WORKFLOW_PATH:-/workflow/workflow.yaml}"`
  and `compose.yaml:39` still sets that path. That is a code change, so the page now opens
  with a **status section** saying the harness has not been ported, that the current CLI
  refuses a path, and what the ported shape would be — with the `WORKFLOW_DIR` /
  `WORKFLOW_PATH` rows marked as documented-as-they-behave. Two live errors alongside it: the
  `hello-world` smoke test it recommended cannot work (that workflow is a Python package now,
  so the paragraph now sends the reader to `workhorse run hello-world --dry-run` on the host),
  and the config row named `WORKHORSE_CONFIG` at `~/.config/workhorse/config.toml` — the
  unified key is `STABLEMATE_CONFIG` at `~/.config/stablemate/config.toml`, with the old
  spelling honored as a legacy alias (`core/stablemate_core/config.py:38-41`).
- **`docs/features/workhorse/flows/workhorse-author-test.md` — a broken example I wrote in
  iteration 4.** Step 3 offered `RunEnv(run_agent=scripted)`. `RunEnv` has **no `run_agent`
  field**; the seam is `agent_runner: AgentRunner | None`, and `None` means "build the real
  ladder from `config` at the first turn", which is why a workflow with no agent node never
  resolves a backend. Corrected, with the `StubRunner` shape named.
- **`workhorse/workhorse/testing.py`'s module docstring** — finding 1 of iteration 4, which
  that entry explicitly deferred to item 4 as "every runnable example". Its example imported
  `drive` and `stub_nodes` from `workhorse.pyflow` (which exports neither), called `drive`
  without its required `env`, and used the pure function `stub_nodes(index) -> index` as a
  context manager. Replaced with the real `RunEnv` construction, pointing at
  `workflows/tests/test_hello_world.py` as the same example in running code. Docstring only —
  no behaviour changed.
- **Root `pyproject.toml`** — said "Each workflow.yaml declares the tools it needs in a
  `requires:` block instead", present tense, and described the base library's payload as
  `library/, scaffolds/, workflows/`. Two of those three directories are gone. Both corrected.

#### The end condition's `ostler` clause has moved, and 19 of its errors are false

**Finding 20 is obsolete and is withdrawn.** It recorded that `ostler doctor` checks `code:`
targets only and cannot see Markdown links or anchors. It can now — the concurrent workstream
added `ostler/ostler/links.py` and a `missing-anchor` finding. The end condition's "`ostler`
reports no dangling references" is therefore a checkable claim for the first time.

The count is now **58**: 32 `dangling-code-ref`, 7 `missing-code-symbol`, 19 `missing-anchor`.
**All 19 anchor errors are false positives**, and from a single one-character bug:

```python
_ANCHOR_SPACE_RE = re.compile(r"\s+")          # ostler/ostler/model.py:467
return _ANCHOR_SPACE_RE.sub("-", s).strip("-") # …collapses runs
```

github-slugger replaces **each** whitespace character with its own hyphen and does **not**
collapse runs. So `## \`resolve_workspace\` — build the repo map` strips to
`resolve_workspace␣␣build the repo map` (the em-dash is dropped, its two flanking spaces are
not) and slugs to `resolve_workspace--build-the-repo-map`. Ostler computes
`resolve_workspace-build-the-repo-map` and reports the correct link as broken. Every heading
in this book is `Name — description`, so the bug fires on every intra-page link in the book
and *only* on correct ones. Confirmed independently: a checker matching github-slugger exactly
reports **0 broken links across 313 tracked markdown files**, path and anchor. This is the
same mistake this loop made in its own checker in iteration 9 and fixed empirically against
GitHub's renderer.

That leaves **39 real errors**, unchanged in substance from iteration 8's count and all of
them item 3's remaining work: the 32 `dangling-code-ref` are `concepts/` pages still grounded
on the pre-refactor `runner/agent.py`, and 6 of the 7 `missing-code-symbol` are farrier's
`install.py` (a concurrent-workstream split, not this port). `concepts/testing.md` no longer
contributes any — the question left open last iteration about an unaccounted-for eighth
`missing-code-symbol` is settled: its `::WorkflowRun*` citations were among them, and the
rewrite removed them.

#### Findings — code the docs cannot describe truthfully (no code changed)

25. **`ostler`'s anchor slugifier collapses whitespace runs** (`ostler/ostler/model.py:467`),
    so every `X — Y` heading — the house style of the entire OKF book — yields a slug one
    hyphen short of GitHub's. It reports 19 correct links as `missing-anchor` and would
    report a genuinely broken `--` link as fine. One regex: replace each whitespace character
    rather than each run. Not made here; this loop changes no behavior.
26. **The Docker harness is un-ported, not merely mis-documented.** `entrypoint.sh:136` and
    `compose.yaml:39` still pass `--workflow <path>`, which the current CLI refuses, so the
    containerized route fails at startup. This supersedes and widens finding 16, which named
    only the entrypoint line.
27. **`farrier`'s generated launcher has one dead branch, not a dead default.** Checked
    before writing this down, because the obvious reading is wrong: `agents.mk`'s
    `--workflow $(WORKFLOW_ARG)` (launcher.py:190, 197) is *correct* in the default case —
    `WORKFLOW_ARG` falls back to `$(WF)`, a bare **name**, and `main._main` injects the
    `run` subcommand when argv starts with something that isn't one, so
    `workhorse --workflow coder …` still works exactly as the comment at launcher.py:129
    claims. What is dead is the **`WORKFLOW_DIR` override**:
    `WORKFLOW_ARG := $(if $(WORKFLOW_DIR),$(WORKFLOW_DIR)/workflow.yaml,$(WF))`
    (launcher.py:134) appends a filename that no longer exists to a directory the CLI would
    refuse anyway, so `make agent-native WORKFLOW_DIR=…` — documented as "pin a specific
    checkout" — cannot work. The compose the same module emits sets
    `WORKFLOW_PATH: /workflow/workflow.yaml` (launcher.py:361), which is finding 26 again in
    every installed repo. Both are code changes.
28. **`benchmarks/bench.py`'s staleness guard is silently dead.** It computes the newest
    workflow-source mtime by globbing `WORKFLOWS/*/{workflow.yaml,scripts/*.py,prompts/*.md}`
    (line 475) where `WORKFLOWS = base-library/workflows` (line 84) — a directory that no
    longer exists. Every pattern matches nothing, so `newest_src` takes its `default=0.0`
    and every run compares as newer than the code. The comment above it explains that this
    check exists precisely because a report scoring stale artifacts is "the same vacuous
    success it exists to detect" — and it now always passes.

### Iteration 12 — the ladder family, which needed re-grounding rather than re-pointing

Nine `concepts/` pages describing what is now `runner/ladder.py`, `runner/caps.py` and
`runner/reframe.py`. The tempting reading of `ostler`'s `dangling-code-ref` output is that
these pages are *correct documents with stale `code:` pointers* — fix the path, move on.
Reading `ladder.py` and `caps.py` in full first showed that is wrong for this family: loop 2
turned `run_agent` from a module function reading import-time env constants into
`AgentRunner`, a **frozen dataclass whose backend, resilience policy and clock are injected**.
That changes the *contracts* these pages state, not merely where the symbol lives. Three
documented behaviours were flatly false:

- **`invoke-claude.md` documented a fallback that no longer exists.** Its contract had
  `backend: AgentBackend | None (default None)` resolving through `get_backend()` when
  omitted. The shipped docstring says the opposite in as many words: "``AGENT_CLI`` is read
  once at the CLI boundary and the chosen adapter is handed down, so the ladder names no CLI
  and imports none."
- **Every retry counter had moved from a parameter or a module constant to an
  `AgentResilience` field.** `max_invoke_retries`, `max_output_retries`, `_MAX_CAP_WAITS`,
  `_INVOKE_BACKOFF_BASE_S`, `_CAP_TICK_S`, `_CAP_WAIT_MARGIN_S` and the rest are one field
  each on the run's resilience policy (`config_run.py`, whose module docstring makes the
  point: "``from_env`` is the *only* place these variables are read"). A test states a bound
  now instead of setting an env var, and the pages said otherwise.
- **`run-agent.md` claimed the console echoes the resolved prompt variables.** Its setup step
  read "Echo the prompt summary (template path + resolved variable values)". The shipped code
  writes the rendered prompt to `<run_dir>/<node_id>/prompt.md` and prints **only that path**.
  A doc promising that variable values reach the terminal is a privacy claim in the wrong
  direction, so this is corrected rather than softened, and the new page cites the test that
  pins it (`test_rendered_prompt_is_written_and_only_path_is_printed`).

Smaller corrections, all against source: `parse_reset_seconds`' `now` is **required and
positional** (no `datetime.now()` default — the docstring: "a parser that reads the clock
cannot be exercised without one"); `cap_delay_seconds`' text-parse branch now labels from the
*injected* now, not a fresh `datetime.now()`; `sleep_with_notice` emits `otel.heartbeat` once
before the first chunk and after **every** chunk including the last, which no version of the
page mentioned; `timeout_retry_prompt` rounds with `max(1, int(round(...)))`.

**One rename, and only one.** Of the nine slugs, seven already matched their new public name
(the functions only lost a leading underscore), and `run-agent` is not false — it is the
agent-node ladder, it has 19 inbound files, and the STOP rule says rewrite rather than delete
a subject that survives. `invoke-claude` was actively misleading: the unit names no CLI and
resolves none. It became `agent-turn.md` via `git mv`, and the page carries a blockquote
saying it was `invoke-claude.md` and why, so a reader arriving from an old link learns the
reason rather than meeting a 404. Four inbound references outside the family
(`claude-backend.md`, `extract-outputs.md` ×2, `stream-subprocess.md` ×3) were re-pointed;
the rest of those pages is iteration 13/14 work and was left alone deliberately.

`dangling-code-ref` for the book: **32 → 24**, of which 1 is groom's (`.toast`, pre-existing)
and 23 are the still-unported backend/stream pages. `missing-code-symbol` moved 7 → 9, both
new ones in farrier's `install.py` — a concurrent workstream's split, not this port.
`missing-anchor` holds at 19, all finding 25. Zero broken markdown links across all 313
tracked files.

**Open call for the next iteration.** The work order says "regenerate grounded content with
the builder rather than hand-writing it". These nine were hand-grounded, and that was the
right call *for these nine*: what needed correcting was which collaborators are injected and
which contracts became false — judgment about the refactor's intent that a regeneration pass
does not supply. The remaining 16 backend pages are a different shape — a near-mechanical
`backends.py` → `backends/<cli>.py` split with the symbol names largely intact — and are the
better candidate for an okf-builder run.

### Iteration 13 — the backend port and the shared turn machinery

Item 3, the `runner/` remainder, second slice. Six pages, all grounded in modules read in
full first (`runner/failure.py`, `runner/backends/__init__.py`, `runner/backends/registry.py`,
`runner/backends/turn.py`, `runner/backends/jsonl.py` — 625 lines): `classify-turn`,
`finalize-turn`, `read-session-id`, `stream-jsonl`, `agent-backend`, `get-backend`. The
subset was chosen as "everything CLI-agnostic": the five adapter modules stay for
iterations 14–15, so no page here had to describe a CLI it had not read.

**Five flat falsifications, none of them a rename.**

1. **`classify_turn`'s ladder has seven branches, not six.** A new branch sits between cap and
   timeout: `timed_out and is_transient(diagnostics)` raises a transient
   `BackendInvocationError` carrying the *provider's* error rather than a timeout message.
   It exists because `stream_jsonl`'s early abort now sets `timed_out=True` for a reason that
   is not a budget overrun, and reporting that as one would have told an operator to raise
   `AGENT_RESULT_TIMEOUT_S` for a problem that had nothing to do with the timeout.
2. **`classify_turn` writes a second sink.** New `record_session_map(session_id_path, node_id,
   session_id)` puts the id on the open turn span (`otel.turn_session`) *and* appends
   `{"node":…, "session_id":…}` to `sessions.jsonl` beside `.session_id`, swallowing `OSError`
   — so a run's node→session map survives with telemetry off. The page claimed a lone
   `write_text`.
3. **The three marker predicates are public and have second callers.** `is_cap`,
   `is_transient`, `is_context_overflow`, `rate_limit_info` — no leading underscore, and
   `stream_jsonl`'s early abort plus `AgentRunner.turn`'s message scan both call them. The
   page presented them as private helpers of one function, which is exactly the framing that
   would let a future edit change one without checking the other. Renaming the four section
   anchors broke six inbound links, fixed in the same commit.
4. **`finalize_turn` takes a `TurnState`, not four positional accumulators**, and now emits
   `otel.turn_result(state.usage)` under an `is_empty` guard — one emission point for every
   non-Claude turn's cost, and *absent ≠ zero* enforced there rather than per backend.
5. **`stream_jsonl` returns a `TurnState`, not a 4-tuple**, takes `on_event(event, state,
   node_id)` with **three** args, has **two** abort paths (`"cap"` then `"transient"`), and
   now actually honours `cwd` — previously accepted and silently dropped, so Codex, Copilot
   and OpenCode nodes ran in the launching process's working directory regardless of the
   node's `cwd:`. It also layers `env_extra` from `[harness.<backend>].env`.

The port page gained what the module docstrings argue and the old page never said: `AgentBackend`
is an **ABC, not a `Protocol`** (it carries real shared behavior — `harness_env()` — and an
unimplemented method should fail at construction); `backends/__init__.py` declares the port and
nothing else so importing the type drags in no adapter; and `registry.py` is deliberately *not*
`__init__.py` for the same reason. `harness_env()` is read **per turn**, not captured at startup.

**Answering iteration 12's open call: no.** That entry predicted the remaining backend pages
were "a near-mechanical split with the symbol names largely intact" and therefore the better
candidate for an okf-builder run. For this subset that prediction is wrong — `classify_turn`
gained a ladder branch and a session-manifest sink, `finalize_turn` changed arity and gained
telemetry, `stream_jsonl` changed its return type and fixed a silent `cwd` bug. Loop 2 rewrote
these units, it did not move them, and hand-grounding was again the only way to catch it. The
prediction may still hold for the five *adapter* pages; it does not hold for shared machinery,
and the distinction is worth carrying into iteration 14 rather than re-testing blind.

Four public symbols also lost their documented underscore across the whole book
(`stream_jsonl`, `finalize_turn`, `read_session_id`, `classify_turn` — 14 files), so no page
names a symbol that does not exist even where the rest of the page is still iteration-14 work.

`dangling-code-ref` **24 → 24** (this slice's six pages were already correctly pointed at their
new modules by loop 2's own edits, or were re-pointed here without changing the count: the 23
book entries are the still-unported adapter/stream pages plus groom's pre-existing `.toast`);
`missing-code-symbol` 9 → 8; `missing-anchor` 19 → 21, all finding 25 — ostler's slugifier
collapses runs of hyphens where GitHub's does not, and the new
`#early-abort--stop-the-clis-own-retry-loop` heading has two. Zero broken markdown links across
all 313 tracked files by the GitHub-accurate checker. `ruff check .`, `make test` and
`make check-public` all green.

### Iteration 14 — the four non-Claude adapters, where one callback became an object

Item 3, the `runner/` remainder, third slice. Nine pages, all grounded in the four adapter
modules read in full first (`runner/backends/aider.py`, `codex.py`, `copilot.py`,
`opencode.py` — 608 lines): `aider-backend`, `run-text-turn`, `codex-backend`,
`codex-on-event`, `codex-reset-at`, `copilot-backend`, `copilot-on-event`,
`opencode-backend`, `opencode-on-event`. The Claude family (`backends/claude.py`, 371 lines)
and `stream-subprocess.md` are iteration 15.

**Answering iteration 13's carried-forward question: no, again — and for a sharper reason.**
Iteration 12 predicted the adapter pages would be "a near-mechanical split with the symbol
names largely intact"; iteration 13 found that false for shared machinery and left open
whether it held for the adapters. It does not. Loop 2 did not merely move these functions:

1. **All nine `code:` targets named the deleted `runner/backends.py`.** That much *was*
   mechanical. Nothing else was.
2. **The three prefixed callbacks are now one unqualified `_on_event` per module** —
   `_codex_on_event`/`_copilot_on_event` → `codex.py::_on_event`, `copilot.py::_on_event`;
   module scope supplies the disambiguation the prefix used to.
3. **OpenCode's callback is no longer a function at all.** It is
   `_OpenCodeEvents.on_event`, a bound method on a `@dataclass(slots=True)` constructed
   fresh per turn. The old page documented a `state["_text_parts"]` key the adapter "lazily
   adds… not part of `stream_jsonl`'s own contract" — that hack is gone, and the module
   docstring says why: *a struct shared by N implementations holding one implementation's
   private key is exactly the shape the shared module must not have*. The per-turn instance
   is also what makes cross-turn leakage structurally impossible, which
   `test_opencode_text_parts_do_not_leak_between_turns` now pins. A page cannot be
   "re-pointed" through that change; it has to be rewritten.
4. **Usage accounting is entirely new, and every page described it as absent.** All four
   adapters now populate `TurnState.usage`: codex on `turn.completed`, copilot on `result`,
   opencode on `step_finish` (a **merge**, since a turn has several steps), aider by regex
   over the transcript via `usage.from_text`. The old pages listed these event types under
   "silently ignored".
5. **Signatures across the board.** `on_event` is 3-arg over a `TurnState`, not 4-arg over a
   dict plus a diagnostics list; `finalize_turn` takes 5 positionals, not 8; `stream_jsonl`
   requires `resilience=` and takes `cwd=`/`env_extra=self.harness_env()`; every `run_turn`
   and `compact` has keyword-only **required** `timeout`/`resilience` where the pages still
   showed `timeout=DEFAULT_RESULT_TIMEOUT_S` defaults.
6. **`_agent._is_cap(diagnostics)` → the public `failure.is_cap(state.diagnostics_text)`.**
7. **`_codex_reset_at` moved into `opencode.py`, not `codex.py`**, along with
   `_OPENCODE_AUTH_PATH`, `_CODEX_RESPONSES_URL` and `_OPENCODE_VARIANT` — it lives beside
   its only caller, and despite the name is not part of the codex backend at all. The page
   now says so.

**One code/docstring disagreement, reported not fixed** (this loop changes no behavior):
`CopilotBackend`'s class docstring says `--allow-all-tools + --no-ask-user`, while `run_turn`
emits `--allow-all`. The code wins, so the pages document `--allow-all`; the stale docstring
is a one-word fix for whoever next touches that module.

**Three real model names were replaced with placeholders while rewriting** — a live
OpenRouter model on the aider page, a provider model and a local Ollama tag on the codex
page, and another OpenRouter model on the opencode page — now `openrouter/example-org/…`,
`example-org/example-model-v3.1`, `example-coder:32b`. Documenting the real setup is the
standing temptation of a docs pass; `make check-public` passed both before and after, which
is the point: it gates private *project* names, not the general public bar.

Ten tests the old pages never cited are now `verify:` targets, found by grepping
`test_backends.py` rather than by trusting the pages
(`test_codex_on_event_extracts_text_and_session`,
`test_copilot_on_event_extracts_text_and_session`,
`test_opencode_text_parts_do_not_leak_between_turns`,
`test_codex_effort_sets_reasoning_override`, `test_codex_no_effort_omits_override`,
`test_codex_profile_from_env`, `test_codex_profile_at_slug_model_string`,
`test_aider_run_turn_builds_noninteractive_cmd`, `test_aider_effort_clamped_to_high`,
`test_aider_no_effort_omits_flag`).

The two inbound anchors into this slice — `aider-backend.md#_aider_effort` (from
`claude-backend.md` and `run-claude-cli.md`) and `opencode-backend.md#contract` (from
`codex-reset-at.md`, twice) — were enumerated *before* rewriting and preserved, so no
rewrite broke a link. `opencode-on-event.md`'s broken self-link
`[OpenCodeBackend.run_turn](#related-pieces)` and its ungrounded prose reference to
`backends.py::OpenCodeBackend` both became real links to `opencode-backend.md`.

`dangling-code-ref` **24 → 9** (the eight remaining book entries are the Claude family and
`stream-subprocess`, iteration 15's slice, plus groom's pre-existing `.toast`);
`missing-code-symbol` 8 → 8; `missing-anchor` 21 → 22, the increase being one more link to
the same `#early-abort--stop-the-clis-own-retry-loop` heading — still finding 25, ostler's
slugifier collapsing hyphen runs where GitHub's does not. Zero broken markdown links across
all 313 tracked files by the GitHub-accurate checker. `ruff check .`, `make test` and
`make check-public` all green.

### Iteration 15 — the Claude family, where the adapter turned out to own the protocol

The last of item 3's `runner/` remainder: the six pages grounded in
`runner/backends/claude.py` (`claude-backend`, `run-claude-cli`, `compact-session`,
`stream-events`, `emit-event`, `tool-summary`) plus `stream-subprocess`, now
`runner/process.py`. Every one of the seven still pointed `code:` at `runner/agent.py` or
`runner/backends.py`, neither of which exists.

What the pages asserted, and what the code says:

1. **The adapter/implementation relationship is inverted.** The pages said `ClaudeBackend`
   "owns no protocol code itself: it is a thin **adapter** over the existing Claude
   functions in `runner/agent.py`". It is the opposite now, and deliberately: the module
   docstring records that the protocol *used* to live in the CLI-agnostic ladder with the
   facade delegating back into it, "which made the generic ring the home of one
   implementation and forced the ladder and `backends` to import each other lazily. Claude
   is now a sibling of every other adapter and the ladder imports it not at all." This was
   the one falsification worth a full rewrite rather than a re-point — it reverses the
   page's thesis, not a detail in it.
2. Following from that: the "imports the `agent` module (not its names), so a monkeypatched
   function resolves at call time and no import cycle forms" bullet is **entirely dead**.
   Both of its reasons died with the split; `claude.py` imports `AgentBackend` at module
   scope like any other adapter.
3. `_run_claude_cli` → **`_run_cli`**. The qualifier existed because the function once sat
   in the ladder among functions belonging to no backend in particular; one module per CLI
   supplies that disambiguation now. `run-claude-cli.md` was retitled but keeps its slug and
   filename — ostler node ids are path-derived, and three inbound `#algorithm` links depend
   on it.
4. `run_turn`/`compact` take keyword-only **required** `timeout`/`resilience` — no
   `DEFAULT_RESULT_TIMEOUT_S` default anywhere in this family — and **both** forward
   `env_extra=self.harness_env()`. `compact-session.md` documented neither `resilience` nor
   `env_extra`; the code comment is explicit about why the second one matters ("same
   harness, same environment: a knob that shapes the turn must also shape the `/compact`
   turn"), and `test_compaction_runs_under_the_same_env` holds it.
5. **`ClaudeTurnStream` is new** and undocumented anywhere — a `@dataclass(slots=True)` that
   "replaces a seven-element tuple every caller had to decode by counting positions", which
   is exactly what `stream-events.md` still documented as the return type. It is *not* the
   shared `TurnState` from iteration 13, and the reason is structural: the four JSONL/text
   backends go through `finalize_turn`, which calls `classify_turn` on their behalf; Claude
   calls `classify_turn` itself, so it needs an accumulator shaped for that call. Both
   rewritten pages now link a new `## ClaudeTurnStream` section.
6. `_stream_events` gained an **unconditional** `otel.turn_result(usage.normalize(event))` on
   every result event, and a `rate_limit_event` → `failure.rate_limit_info` branch feeding
   `rate_limited`/`rate_reset_at`. The unconditional call is not a contradiction of iteration
   13's note that `finalize_turn` guards the same call on a non-empty usage — different code
   paths, and the code comment gives the reason ("Claude's result event carries
   `duration_ms` even when it reports no tokens").
7. `stream_subprocess` moved to `runner/process.py` and gained required
   `resilience`/`env_extra`. The module around it grew substantially and none of it was
   documented: the `ActiveProcess` class (handle **and** lock as one object rather than "two
   module globals two functions happen to share" — the page still described `_active_proc` /
   `_active_proc_lock`), `_spawn_streaming` with `_EXEC_BUSY_ERRNOS` and its
   self-update exec-retry loop, the `otel.turn_event("exec_retry"/"watchdog_kill")` and
   `otel.turn_heartbeat` emissions, and `fired = threading.Event()` in place of the
   `fired["v"]` dict cell.
8. `_WATCHDOG_GRACE_S` **is gone as a module constant** — the grace is
   `resilience.watchdog_grace_s`, read off the argument. The page presented it as a
   module-level env-backed constant, which is precisely the shape a per-run override cannot
   affect.
9. `terminate_active` is called from **`pyflow/run.py`**'s `KeyboardInterrupt` and
   `PyflowError` handlers — not, as the page said, "`main.py`'s top-level
   `KeyboardInterrupt`, `OutOfGasError`, and `BackendInvocationError` handlers".
   **`OutOfGasError` does not exist in the tree**; `pyflow/errors.py` defines `PyflowError`
   and six subclasses, none of them that.
10. `stream-subprocess.md` pointed `stream_jsonl` and `_run_text_turn` at
    `runner/backends.py`; they are `runner/backends/jsonl.py` and `runner/backends/aider.py`.
11. `compact` is `@abstractmethod` on the port, so the four non-Claude backends each
    implement it as a bare `return False` — they do not inherit a default. The page's
    phrasing implied an inherited one.

**Finding, not fixed (a code nit, and this loop changes no behavior):**
`stream_subprocess`'s `on_line` parameter is annotated `Callable[[str], None]`, but the loop
honors a truthy return as an early-abort request and `stream_jsonl` depends on that. The
annotation understates the runtime contract. The page documents the contract as it actually
is and says so explicitly.

`emit-event.md` and `tool-summary.md` needed only their `code:` targets re-pointed — their
algorithms survived the move verbatim, which is the expected shape for two functions that
only format log lines.

`dangling-code-ref` **9 → 2**: groom's pre-existing `.toast` and `extract-outputs.md`, which
belongs to the `scriptutil`/`extract-outputs`/`render-prompt` de-YAML remainder rather than
to this slice. Every Claude-family and `process.py` reference is now grounded.
`missing-code-symbol` 8 → 8; `missing-anchor` 22 → 23, the increase being one more link to
`#early-abort--stop-the-clis-own-retry-loop` — still finding 25, ostler collapsing hyphen
runs where GitHub does not. Zero broken markdown links across all 313 tracked files by the
GitHub-accurate checker. All ten inbound anchors into this slice were enumerated before
rewriting and preserved. `ruff check .`, `make test` and `make check-public` green.

### Iteration 16 — farrier's `install.py` split, and an ostler blind spot

`farrier/farrier/install.py` is now a 219-line compatibility facade that **declares nothing**:
`grep -nE '^(def |class )'` returns no lines. It re-exports from twelve capability modules so
`farrier.install:main` (still the declared console script) and historical
`from farrier.install import ...` call sites keep resolving. Six pages of the farrier book
pointed 21 `code:` targets at it. All 21 are re-pointed; twelve distinct symbols resolved as:

| doc target | real home |
|---|---|
| `main` | `farrier/farrier/cli.py:439` |
| `resolve_library_dir` | `farrier/farrier/layers.py:126` |
| `Renderer` and its seven methods | `farrier/farrier/renderer.py:94` |
| `skill_metadata_block` | `farrier/farrier/renderer.py:40` |
| `frontmatter_metadata` | `farrier/farrier/frontmatter.py:69` |
| `render_expected` | `farrier/farrier/outputs.py:130` |
| `is_library_dir` | `core/stablemate_core/layout.py:12` |
| `read_config` | `core/stablemate_core/config.py:384` — an **alias assignment**, `read_config = load_config`; the honest `code:` target is `load_config`, with the farrier spelling explained in prose |
| `write_library_dir` / `write_stablemate_dir` | `core/stablemate_core/config.py:387` / `:392` |
| `set_library_globals` | **nothing — the mechanism is gone** |
| `_write_config_key` | **nothing — `write_config_key` at `config.py:214`, no underscore** |

Found untrue, beyond the paths:

1. **`library-directory.md`'s entire "Module globals populated" section.** It documented
   `set_library_globals(root)` pointing eight `farrier.install` globals (`AGENTS`, `LIBRARY`,
   `PACKS`, `SKILLS`, `PROMPTS`, `ROOTS`, `SCAFFOLDS`, `WORKFLOWS`) at one library root. No
   such globals exist — `grep` for any of the eight in `farrier/farrier/*.py` returns nothing.
   The subject survives under a new name, so it was **rewritten, not deleted**, per the STOP
   rule: `set_layers(overlay)` builds an ordered `LAYERS` stack (overlay, then base) and
   lookups go through `layer_dirs` / `find_in_layers` / `available_names` / `searched_layers`.
   The old globals' paths are now `parts` tuples: `("library", "skills")`,
   `("library", "roots", f"{root}.md")`, `("workflows", name)`.
2. **"A usable library must contain both `library/` and `packs/`."** `is_library_dir` requires
   only `library/`; `packs/` is deliberately optional, since the base ships skills and
   scaffolds with no packs at all. Stated on two pages.
3. **"If none of the three yield a candidate, it raises `SystemExit`."** It returns `None` when
   a base library is installed — base-only is a supported setup, and the one a reader with no
   configuration gets. `SystemExit` is raised only with neither overlay nor base.
4. **The home config's identity.** It is not farrier's: it is
   `platformdirs.user_config_dir("stablemate")`, not `…("farrier")`, and it is owned by
   `stablemate_core.config`. The page missed `base_dir`, missed `config_version` and its
   `ConfigVersionError` guard, missed the legacy-path merge (`workhorse` then `farrier`, only
   when the unified file is absent and the path was not named explicitly), and described the
   writer as emitting hand-escaped `key = "value"` lines — it uses `tomli_w`, and the change
   was load-bearing: the string version stringified nested tables, so one `config set-base`
   turned `[power.*]` into a Python-repr string and every node silently fell back to the
   default model.
5. **"Missing root names are silently skipped"** (`renderer.md`). `render` validates the whole
   `roots` selection up front and raises with the unknown names, the layers searched and the
   names that do exist; the per-root miss check survives only as a guard for a
   directly-constructed `Renderer` in tests. Workflows are validated the same way — not with
   the documented `SystemExit("Unknown workflow: <name>")`.
6. **A dead `verify:` target.** `library-directory.md` cited
   `farrier/tests/test_config_resolution.py::test_set_library_globals`; that test is gone.
   Replaced with the three tests that do cover the successor —
   `test_no_overlay_is_fine_when_base_is_installed`, `test_overlay_shadows_base`,
   `test_unknown_pack_names_the_layers`.

**Finding 26 — ostler's `missing-code-symbol` check only visits node-level `code:` bullets.**
Of the 21 `install.py` targets across those six pages, ostler flagged **8**. Every flagged one
is the *first* `code:` bullet in its file (the node's own), plus `farrier.md#version`, which is
a sub-node with a heading. The other 13 sit in sections that are not ostler nodes and are never
checked — which is exactly how `set_library_globals` and `_write_config_key`, symbols that
exist nowhere in the tree, stayed invisible to the checker while the page describing them was
read as verified. This is the "if it cannot report this, say so instead of grepping around it"
case: reported here rather than worked around, since fixing it is engine work and this loop
changes no behavior. Until it is fixed, a page's non-node `code:` bullets are unverified and a
grep is the only check.

Every farrier `missing-code-symbol` is cleared; the single survivor repo-wide is
`scriptutil.py::_read_workspace_file`, part of the de-YAML remainder. `dangling-code-ref`
2 → 2 and `missing-anchor` 23 → 23 (untouched by this slice); `ostler doctor` totals
**34 → 26**. Zero broken markdown links across 313 tracked files. `ruff check .`, `make test` and
`make check-public` green.

### The green gate, and a concurrent workstream

`make test` is **red in the working tree and green at `HEAD`**, re-verified each iteration
by running the failing files in a detached worktree at `HEAD`. At iteration 2 the 13
failures were an uncommitted refactor of `workhorse/workhorse/runner/agent.py`
(`_invoke_claude(..., resilience=)`); at iteration 3 they had moved to
`workhorse/workhorse/runner/backends.py` (`_finalize_turn`, `_codex_on_event`,
`_opencode_on_event` all gaining parameters), which was last written **two minutes** before
the run — `test_backends.py` + `test_agent_cap.py` are **56/56 at `HEAD`** in a clean
worktree. Two consecutive `make test` invocations in the same iteration disagreed with each
other, which is the signature of another workstream editing mid-run rather than of a real
regression. Loop 3's iterations touch Markdown and one docstring, and commit only their own
paths. `ruff check .` and `make check-public` are both clean.

At iteration 5 the failure had moved again: an **untracked** `workhorse/workhorse/runner/backends/`
package now shadows the tracked `runner/backends.py`, and `get_backend` is not importable
from it — 11 failures in `test_agent_cap.py`. In a detached worktree at `HEAD`,
`test_agent_cap.py` + `test_backends.py` are **57/57**.

At iteration 6 it is **green again in the working tree**, with no worktree needed: `e68067f`
committed that `runner/backends/` package, which is what the untracked copy had been
shadowing. `make test`, `make check-public` and `ruff check .` all pass.
