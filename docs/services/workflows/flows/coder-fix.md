---
type: flow
slug: coder-fix
title: Coder standalone fix flow
---
# Coder standalone fix flow

- The `coder.fix` package exports `Fix` (defined at
  `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix`). It is the directly runnable copy of
  the drain; the main coder graph has a separate nested copy and does not hand off to this package.
- The standalone `Fix` machine drains only items filed in the coder backlog. Each selected
  bullet becomes a one-acceptance-criterion fix story, is fixed and checked by one owner turn,
  gated against the repositories that actually changed, documented, and committed before the next
  draw. It is entered directly with `workhorse-coder run fix`.
- The owner turn runs in the item's one story conversation. Its subagents fix the item and QA it, so
  the flow has no separate QA or QA-retry state and never marks a backlog bullet blocked.
- `MAX_LAPS` bounds the gate-repair laps. A still-red gate after the last lap is an operator
  block, not a failed or abandoned item; the rendered command, working directory, and gate output
  are preserved for the resumed owner turn.
- The selected backlog bullet is not mutated during selection. It remains available for a resumed
  run to seed the same story, and is removed only after the gates are clean.
- detail: [coder backlog contract](../concepts/coder-backlog-contract.md)
- The `workspace` name is an optional checkpointed input. An empty value resolves from the
  repository context, and `target_env` defaults to `local` for the documentation handoff and QA.
  `operator_mode` defaults to `auto`.
- The owner turn renders `fix-item.md` with the bullet text, story identity, QA directory,
  documentation path, target environment, the operator's last answer, and the report of the gate
  that failed on the previous lap. It returns an `ImplResult`; a blocked result goes to the block
  path and never reaches the gates on an unchanged tree.
- `render_gate` formats a `FailureReport` as the owner prompt's report section: the source gate,
  working directory, command, and fenced output. The report is preserved across an
  exhausted-budget operator wait.
- `setup` resolves the workspace before selection because this lane has no story context until
  `start` seeds the first item. `start` records the selected `StoryPaths` as the iteration's
  source of truth, so resumed states read the same story rather than drawing a replacement.
- `check` iterates `GATE_ORDER` for each repository with changed paths and keeps the first dirty
  gate of each. Clean gates prune the backlog bullet and move on to `document`. Dirty gates send
  the joined reports back to `work` while laps remain, and block once the laps run out.
- A block is answered by the `resolve` turn in `auto` mode. In a human operator mode, or once
  `MAX_BLOCKS` blocks have been spent, the flow awaits the operator with the story's context file.
- `document` hands off to `Docs` after pruning. The handoff result is accepted only
  for `passed` or `not_applicable`; any other result raises `WorkflowFailed`, leaving the agent's
  implementation commit intact but preventing the standalone drain from continuing.
- `commit` calls `commit_story` with `kind="fix"` and the repositories reported by
  `_changed_dirs`, then returns to `start`. It does not create a branch, push, open a pull request,
  or include an untouched workspace repository.
- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-coder.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-coder.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [coder fix package](../concepts/coder-fix-package.md)
- detail: [coder main flow](coder-main.md)

- tests: `workflows/tests/coder/fix/test_flow.py::test_one_item_is_seeded_fixed_checked_pruned_and_committed`
- tests: `workflows/tests/coder/fix/test_flow.py::test_an_untouched_repo_is_neither_gated_nor_committed`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_docs_sub_flow_runs_for_real_and_its_verdict_gates_the_commit`
- tests: `workflows/tests/coder/fix/test_flow.py::test_documentation_that_blocks_parks_and_keeps_the_agent_commit`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_commits_land_on_the_branch_the_repos_were_already_on`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_first_pass_is_handed_the_item_and_no_report_at_all`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_drain_keeps_going_until_the_section_is_empty`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_run_killed_after_the_owner_turn_does_not_run_it_again`

The flow resolves its workspace once because no story exists at setup time. Each iteration then
selects without mutating the backlog, creates the `fixes` story bucket when needed, and guards the
seeded story file before any agent turn. Only repositories with paths reported by `changed_files`
are gated and committed; repositories merely listed in the workspace manifest are ignored.

The stages, in order: [draw-and-seed](#draw-and-seed), [own-the-item](#own-the-item), [gates](#gates), [operator-block](#operator-block), [document](#document), [commit-and-redraw](#commit-and-redraw).

The flow starts when the configured documentation root resolves before a backlog item is drawn; or when the workspace directories resolve before a backlog item is drawn; or when the backlog contains a non-blocked item in the `Filed by coder` section.
It ends in one of these ways: an empty or entirely blocked backlog returns `Done` without starting another item; an item whose gates are clean is removed from the backlog; a pruned item is documented through the Docs flow; a documented item is committed as one scoped `fix` commit on the current branch; an owner turn that reports a block waits for an operator; an exhausted gate-repair budget waits for an operator.

## Steps

### draw-and-seed

- kind: seed

`setup` resolves the workspace directories. `start` selects the next non-blocked `Filed by coder`
bullet. A dry selection returns `Done`; otherwise the bullet is seeded as a one-AC story, its story
paths are prepared, and the story file must be readable before `work` begins.

### own-the-item

- kind: run

`work` renders `fix-item` with the selected bullet, story paths, epic identity, the operator's last
answer, and the previous lap's gate report. The owner plans, writes the repair, and QAs it in one
high-power session. A blocked result goes to the block path.

### gates

- kind: verify

`check` calls `render_gate` (defined at `workflows/src/workhorse_workflows/coder/fix/flow.py::render_gate`) to format each gate failure report. It asks every changed repository to run each gate in `GATE_ORDER`, using the repository's own
`make <gate>` fallback when no service-specific command is configured. Clean or skipped gates pass.
A dirty gate produces a `FailureReport`; while laps remain, the reports re-enter `work`, and the
still-red final lap enters the block path with the failure output preserved.

The changed-repository set comes from `changed_files`, not from every repository named by the
workspace manifest. A repository with no paths for this item is neither gated nor committed.

### operator-block

- kind: drive

Implementation refusals and exhausted red gates take the block path. In `auto` mode `resolve` runs
the shared operator-resolution turn and, when it answers, resumes `work` with the answer. In a human
operator mode, or after `MAX_BLOCKS` blocks, the flow writes the block to the drained story's
`context.md` and returns `Await`. The operator answer is read back into `operator_context` and the
owner turn is resumed.

### document

- kind: run

After pruning, the flow hands the seeded story to `Docs` with the selected documentation
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
