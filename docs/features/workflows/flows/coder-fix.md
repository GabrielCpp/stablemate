---
type: flow
slug: coder-fix
title: Coder standalone fix flow
---
# Coder standalone fix flow

- The `coder.fix` package exports `Fix` and the shared `BLOCKED_NOTE` marker. It is the directly
  runnable copy of the drain; the main coder graph has a separate nested copy and does not hand
  off to this package.
- The standalone `Fix` machine drains only items filed in the coder backlog. Each selected
  bullet becomes a one-acceptance-criterion fix story, is implemented in one agent turn, judged
  against the repositories that actually changed, sent through one QA retry at most, documented,
  and committed before the next draw. It is entered directly with `workhorse-coder run fix`; the
  main Coder machine has a separate nested drain.
- `MAX_FIX_LAPS` is three gate-repair laps. A still-red gate after the third lap is an operator
  block, not a failed or abandoned item; the rendered command, working directory, and gate output
  are preserved for the resumed repair turn.
- The selected backlog bullet is not mutated during selection. It remains available for a resumed
  run to seed the same story, and is removed only after QA passes or annotated as blocked after the
  single QA retry fails.
- detail: [coder backlog contract](../concepts/coder-backlog-contract.md)
- `docs_path` and `workspace_file` are optional checkpointed inputs. Empty values resolve from the
  repository context, and `target_env` defaults to `local` for the documentation handoff and QA.
- The first implementation pass renders `fix-item.md`; a dirty gate renders `fix-item-repair.md`
  with the exact failing command, working directory, and captured output. Both turns return an
  `ImplResult`; a blocked result is an operator wait and never enters QA on an unchanged tree.
- `check` and `recheck` render `qa-fix-item.md` and expect `QaRunResult` with `passed`, `failed`,
  or `blocked`. A failed first verdict is passed verbatim as `qa_notes` to one
  `apply-qa-fixes.md` turn; a blocked apply waits for the operator rather than running a false
  recheck.
- `render_gate` formats a `FailureReport` as the repair prompt's lap number, source gate, command,
  working directory, and fenced output. The lap number is 1-based and the report is preserved
  across an exhausted-budget operator wait.
- `setup` resolves the workspace before selection because this lane has no story context until
  `start` seeds the first item. `start` records the selected `StoryPaths` as the iteration's
  source of truth, so resumed states read the same story rather than drawing a replacement.
- `item` chooses `fix-item` when no gate report exists and `fix-item-repair` otherwise. Both
  turns use the same story conversation and return `ImplResult`; a blocked implementation is
  written to that story's operator context and never reaches `gates` on an unchanged tree.
- `gates` iterates `GATE_ORDER` for each repository with changed paths. The first dirty gate is
  converted to a `FailureReport` and re-enters `item` while repair laps remain; after the third
  dirty lap, `_gate_red` awaits an operator with the final report instead of failing the run.
- `check` and `recheck` are the only QA states. `apply_once` receives the first verdict's notes,
  gets one attempt, and parks if that attempt is blocked; `recheck` prunes only a passing verdict
  and otherwise marks the backlog item with `BLOCKED_NOTE`.
- `document` hands off to `Docs` after pruning or flagging. The handoff result is accepted only
  for `passed` or `not_applicable`; any other result raises `WorkflowFailed`, leaving the agent's
  implementation commit intact but preventing the standalone drain from continuing.
- `commit` calls `commit_story` with `kind="fix"` and the repositories reported by
  `_changed_dirs`, then returns to `start`. It does not create a branch, push, open a pull request,
  or include an untouched workspace repository.
- A successful or flagged item is handed to `Docs`; only `passed` or `not_applicable` permits the
  standalone flow to commit. The commit uses `kind="fix"`, the current branch, the changed
  repositories only, and then returns to `start` for the next draw.
- start: the configured documentation root resolves before a backlog item is drawn
- verify: count(subject="resolved standalone fix workspace", equals=1)
- start: the workspace directories resolve before a backlog item is drawn
- verify: count(subject="resolved standalone fix repositories", equals=1)
- start: the backlog contains a non-blocked item in the `Filed by coder` section
- verify: count(subject="selected drainable fix items", equals=1)
- steps:
  - [draw-and-seed](#draw-and-seed)
  - [implement](#implement)
  - [gates](#gates)
  - [operator-block](#operator-block)
  - [qa-and-retry](#qa-and-retry)
  - [settle-backlog](#settle-backlog)
  - [document](#document)
  - [commit-and-redraw](#commit-and-redraw)
- end: an empty or entirely blocked backlog returns `Done` without starting another item
- verify: count(subject="dry standalone fix draws", equals=1)
- end: a passing item is removed from the backlog
- verify: count(subject="pruned standalone fixes", equals=1)
- end: a passing item is documented through the Docs flow
- verify: count(subject="documented standalone fixes", equals=1)
- end: a passing item is committed as one scoped `fix` commit on the current branch
- verify: count(subject="committed standalone fixes", equals=1)
- end: a second failed QA verdict leaves the item in the backlog with a blocked annotation
- verify: count(subject="flagged non-convergent fixes", equals=1)
- end: a flagged item is skipped by the next backlog draw
- verify: count(subject="skipped flagged fixes", equals=1)
- end: an implementation block waits for an operator
- verify: count(subject="operator-gated implementation blocks", equals=1)
- end: an exhausted gate-repair budget waits for an operator
- verify: count(subject="operator-gated standalone fixes", equals=1)
- detail: [coder main flow](coder-main.md)
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.setup`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.start`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.item`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.gates`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.read_operator_impl`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.check`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.apply_once`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.recheck`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.document`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.commit`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix._changed_dirs`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix._prune`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix._flag`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix._gate_impl`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix._gate_red`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix._qa`
- tests: `workflows/tests/coder/fix/test_flow.py::test_one_item_is_seeded_fixed_checked_pruned_and_committed`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_red_gate_buys_a_repair_lap_and_hands_the_turn_its_output`
- tests: `workflows/tests/coder/fix/test_flow.py::test_qa_gets_exactly_one_retry_and_the_fixer_is_handed_the_first_verdict`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_second_failing_check_flags_rather_than_retrying_again`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_run_killed_mid_check_resumes_at_the_check`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_gate_still_red_when_the_laps_run_out_parks_rather_than_giving_up`
- tests: `workflows/tests/coder/fix/test_flow.py::test_an_untouched_repo_is_neither_gated_nor_committed`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_retry_that_says_it_cannot_parks_instead_of_rechecking_nothing`
- tests: `workflows/tests/coder/fix/test_flow.py::test_an_implementation_turn_that_says_it_cannot_parks_instead_of_qa_ing_nothing`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_blocked_item_is_flagged_and_the_next_draw_skips_it`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_docs_sub_flow_runs_for_real_and_its_verdict_gates_the_commit`
- tests: `workflows/tests/coder/fix/test_flow.py::test_documentation_that_cannot_converge_preserves_the_agent_commit`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_commits_land_on_the_branch_the_repos_were_already_on`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_first_pass_is_handed_the_item_and_no_gate_report_at_all`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_drain_keeps_going_until_the_section_is_empty`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::render_gate`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::BLOCKED_NOTE`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::MAX_FIX_LAPS`
- code: `workflows/src/workhorse_workflows/coder/fix/__init__.py::__all__`

The flow resolves its workspace once because no story exists at setup time. Each iteration then
selects without mutating the backlog, creates the `fixes` story bucket when needed, and guards the
seeded story file before any agent turn. Only repositories with paths reported by `changed_files`
are gated and committed; repositories merely listed in the workspace manifest are ignored.

## Steps

### draw-and-seed

- kind: seed

`setup` resolves the workspace directories. `start` selects the next non-blocked `Filed by coder`
bullet. A dry selection returns `Done`; otherwise the bullet is seeded as a one-AC story, its story
paths are prepared, and the story file must be readable before `item` begins.

### implement

- kind: run

The first `item` turn uses `fix-item` and receives the selected bullet, story paths, epic identity,
and operator context. It plans and writes the repair in one high-power session. A blocked result is
sent to the implementation operator gate. A gate repair re-enters the same story conversation with
the rendered failing command, working directory, and output through `fix-item-repair`.

### gates

- kind: verify

`gates` asks every changed repository to run each gate in `GATE_ORDER`, using the repository's own
`make <gate>` fallback when no service-specific command is configured. Clean or skipped gates pass.
A dirty gate produces a `FailureReport`; up to `MAX_FIX_LAPS` repair laps re-enter implementation,
and the still-red final lap enters the operator gate with the failure output preserved.

The changed-repository set comes from `changed_files`, not from every repository named by the
workspace manifest. A repository with no paths for this item is neither gated nor committed.

### operator-block

- kind: drive

Implementation refusals and exhausted red gates are written to the drained story's `context.md`
and returned as `Await`. The operator answer is read back into `operator_context` and the item turn
is resumed. The standalone flow does not use an automatic resolver or an epic-scoped answer.

### qa-and-retry

- kind: verify

`check` runs `qa-fix-item` against the changed item. A passed verdict proceeds to pruning. A failed
verdict supplies its notes to exactly one `apply-qa-fixes` turn. A blocked retry awaits the operator
instead of rechecking an unchanged worktree; a successful retry enters `recheck`.

### settle-backlog

- kind: verify

`recheck` runs the same QA turn again. A pass prunes the selected bullet. Any other verdict calls
`mark_fix_blocked` with `BLOCKED_NOTE`, preserving the bullet and allowing the next draw to skip it.

### document

- kind: run

After pruning or flagging, the flow hands the seeded story to `Docs` with the selected documentation
root, epic, and target environment. `passed` and `not_applicable` permit continuation. Any other
documentation result raises `WorkflowFailed`, so a pruned item cannot be committed as if its book
entry had succeeded.

### commit-and-redraw

- kind: run

`commit` commits the changed repositories with `kind="fix"`, the story identity, and no push or
pull request. It then returns to `start`, so each drained item receives its own commit and the next
draw is made only after the current iteration has settled. The docs backlog prune is committed
separately by the backlog adapter when pruning; the implementation commit remains a scoped `fix`
commit on each repository changed by the item.
