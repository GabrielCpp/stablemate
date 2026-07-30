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
71 scripts, 19 awaits and 8 sub-flows.

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
| 3 | _this commit_ | The `okf-builder` port — 29 YAML nodes → 12 states + one sub-flow (19 → 6), 11 scripts → `nodes/` by subject, both pyproject tables, 8 end-to-end tests. No driver change |

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

None.

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
