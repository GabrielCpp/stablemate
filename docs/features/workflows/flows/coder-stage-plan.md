---
type: flow
slug: coder-stage-plan
title: Coder stage-plan flow
status: implemented
---

# Coder stage-plan flow

`stage-plan` runs a multi-phase prose plan one phase at a time, without an operator between the
phases. It slices the source document into self-contained per-phase plans, hands each one to
[implement-plan](coder-implement-plan.md) in order, and runs the plan's own repository-wide gate
once at the end over the accumulated tree:

```bash
workhorse-coder run stage-plan --params '{
  "plan_path": "/absolute/path/to/implementation-plan.md"
}'
```

The motivation is review churn. `implement-plan` reviews the *complete* `base..candidate` diff
against the *complete* plan, and permits a fixed number of issue-fix cycles. A plan whose phases
each touch the same subsystem produces a final diff large enough that the reviewer keeps finding
new work, and the run fails on the convergence budget rather than on the code. Running the plan
phase by phase makes each review a review of one phase's diff against one phase's plan, which is
the size the review budget was chosen for.

## States

| State        | What it does                                                                    |
| ------------ | ------------------------------------------------------------------------------- |
| `setup`      | `snapshot_staged_plan` — freeze the plan text and its digest, require a clean, branch-checked-out, exactly-published checkout |
| `start`      | one extra-smart agent turn slices the plan (`prompts/slice-implementation-plan.md`) |
| `prepare`    | `prepare_slices` — deterministic coverage gate, then one plan document per phase written under the run directory |
| `select`     | project the operator worklist; route to the next phase, or to the final gate     |
| `stage`      | `handoff(ImplementPlan, plan_path=<slice file>)`                                 |
| `record`     | `record_stage_outcome` — archive the finished phase and advance the index        |
| `final_gate` | `verify_staged_candidate` in an isolated committed tree, then `complete_stages`  |

## Coverage is checked, not reported

A slicing turn that quietly drops the last two phases of a ten-phase plan would otherwise produce a
run that reports complete having implemented eight. So the declaration is made falsifiable: the
turn reports the phase headings it found, and `prepare_slices` derives the expected list from the
source document itself — every ATX heading at the first declared heading's depth inside its
enclosing section, ignoring headings inside fenced code so a `#` shell comment in a ```bash gate
block is not mistaken for a phase. The declaration must equal that list exactly.

The slices are then checked against the declaration: ids are unique kebab-case, every slice body is
non-empty and carries a heading matching each phase it claims, and the concatenated `covers` must
equal the declared phases exactly and in plan order. The slicing must also declare a non-empty
repository-wide `final_verification`, each command validated by the same argv gate
`implement-plan` uses — no shell, no Git.

Everything here fails closed and fails *before* any phase runs, because the alternative is
discovering incomplete coverage after nine phases of committed work.

## What each phase inherits and what it does not

Each slice is a standalone plan document. The slicing prompt requires it to carry its own
background, file list, tests and acceptance criteria, to state earlier phases as landed fact rather
than as pending work, to say explicitly that later phases are out of scope, and to name only
verification that passes with this phase alone on the tree. A phase that names the whole plan's
gate would fail on work its own slice was never asked to do.

`repo_dir` is declared in `injects`, so it crosses the handoff automatically; the child receives
`plan_path` pointing at the written slice file.

## Evidence survives the next phase

`handoff` is keyed on the workflow class, so all phases share the `implement_plan` artifact scope,
and `ArtifactWriter.at` empties that scope on every fresh entry. Left alone, a nine-phase run would
finish holding only the ninth phase's evidence. `record_stage_outcome` copies
`<run_dir>/implement_plan/_flow` out to `<stage_dir>/phases/<id>` before the next handoff, and
writes `<stage_dir>/phases/<id>.json` with the phase's task count, review issue count, review
passes and final commit. Archiving is its own state so that a failure in it resumes at `record`
rather than re-running the phase.

## Safety boundaries

- Every precondition `stage-plan` asserts at setup is asserted again, authoritatively, by each
  phase's own `implement-plan` snapshot. Repeating them costs the operator a second instead of a
  slicing turn.
- Each phase's plan document is digested when it is written and re-digested before the phase runs;
  a phase implements the document that was checkpointed or nothing.
- Between phases the flow asserts the published state directly: the branch is unchanged, `HEAD` is
  the previous phase's final commit, the worktree is clean, and `origin/<branch>` is at that same
  commit. A phase starts from a published tree or not at all.
- A phase is accepted only if its child returned `complete`, for the digest it was handed, with a
  new final commit.
- There is **no skip-on-failure arm**. Plan phases are a real dependency chain; continuing past a
  failed phase would run later phases against a tree the plan does not describe. A failed phase
  stops the run with every earlier phase's evidence and commits intact.
- There is **no whole-plan review at the end** — that is exactly the churn the flow exists to
  avoid. The aggregate check is the plan's own declared `final_verification`, run deterministically
  in a detached worktree at the published `HEAD`.
- `worklist.json` under the stage directory is a rebuildable operator projection. The checkpointed
  slice list, phase index and outcome list are the execution authority; the projection is never
  read back to schedule work.

The flow inherits `implement-plan`'s trust model unchanged: it is a **trusted-agent workflow, not
an operating-system sandbox**.

## Operator notes

`--dry-run` walks as far as `prepare_slices` and stops there. No static stub reply can satisfy the
coverage gate, which derives its expectation from whichever plan the operator passed, so a stub
that appeared to pass would be a stub that had disabled the check.

## Verification

- `workflows/tests/coder/stage_plan/test_slices.py`
- `workflows/tests/coder/stage_plan/test_flow.py`
- `workflows/src/workhorse_workflows/coder/stage_plan/flow.py`
- `workflows/src/workhorse_workflows/coder/stage_plan/inventory.py`
- `workflows/src/workhorse_workflows/coder/stage_plan/execution.py`
