---
type: flow
slug: coder-fix
title: Coder standalone fix flow
---
# Coder standalone fix flow

- The `coder.fix` package exports `Fix` (defined at
  `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix`). The main coder flow hands off to it
  from its `drain` step once a story's QA passes, and `workhorse-coder run fix` runs it alone.
- The standalone `Fix` machine drains the open `qa` records of the run's workspace repositories on
  the [debt register](../../ostler/concepts/the-debt-register.md). Each drawn record becomes a
  one-acceptance-criterion fix story, is fixed and checked by one owner turn, gated against the
  repositories that changed, documented, committed, and closed as `done` before the next draw.
- The owner turn runs in the item's one story conversation. Its subagents fix the item and QA it,
  so the flow has no separate QA or QA-retry state.
- `MAX_LAPS` bounds the gate-repair laps. A still-red gate after the last lap is an operator
  block, not a failed or abandoned item; the rendered command, working directory, and gate output
  are preserved for the resumed owner turn.
- The drawn record is not changed during selection. It stays open for a resumed run to seed the
  same story, and it is closed only after a commit of the fix lands.
- detail: [coder backlog contract](../concepts/coder-backlog-contract.md)
- The `workspace` name is an optional checkpointed input. An empty value resolves from the
  repository context, and `target_env` defaults to `local` for the documentation handoff and QA.
  `operator_mode` defaults to `auto`.
- The owner turn renders `fix-item.md` with the record's summary as the item text, the story
  identity, QA directory, documentation path, target environment, the operator's last answer, and
  the report of the gate that failed on the previous lap. It returns an `ImplResult`; a blocked
  result goes to the block path and never reaches the gates on an unchanged tree.
- `render_gate` formats a `FailureReport` as the owner prompt's report section: the source gate,
  working directory, command, and fenced output. The report is preserved across an
  exhausted-budget operator wait.
- `setup` resolves the workspace before selection because this lane has no story context until
  `start` seeds the first item. `start` records the selected `StoryPaths` as the iteration's
  source of truth, so resumed states read the same story rather than drawing a replacement.
- `check` iterates `GATE_ORDER` for each repository with changed paths and keeps the first dirty
  gate of each, then checks that the turn left nothing uncommitted. Clean gates and a clean tree
  move on to `document`. Otherwise the joined reports go back to `work` while laps remain, and
  block once the laps run out.
- A block is answered by the `resolve` turn in `auto` mode. In a human operator mode, or once
  `MAX_BLOCKS` blocks have been spent, the flow awaits the operator with the story's context file.
- `document` hands off to `Docs`. The handoff result is accepted only for `passed` or
  `not_applicable`; any other result raises `WorkflowFailed`, leaving the agent's implementation
  commit intact and the record open.
- `commit` calls `commit_story` with `kind="fix"` and the repositories reported by
  `_changed_dirs`, then closes the record and returns to `start`. It does not create a branch,
  push, open a pull request, or include an untouched workspace repository.
- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-coder.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-coder.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [coder fix package](../concepts/coder-fix-package.md)
- detail: [coder main flow](coder-main.md)

- tests: `workflows/tests/coder/fix/test_flow.py::test_one_item_is_seeded_fixed_checked_committed_and_closed`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_drain_keeps_going_until_no_open_qa_record_is_left`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_fix_that_changed_nothing_fails_the_drain_and_leaves_the_record_open`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_run_where_no_repository_landed_a_commit_leaves_the_record_open_and_ends`
- tests: `workflows/tests/coder/fix/test_flow.py::test_an_untouched_repo_is_neither_gated_nor_committed`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_docs_sub_flow_runs_for_real_and_its_verdict_gates_the_commit`
- tests: `workflows/tests/coder/fix/test_flow.py::test_documentation_that_blocks_parks_and_keeps_the_agent_commit`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_commits_land_on_the_branch_the_repos_were_already_on`
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_first_pass_is_handed_the_item_and_no_report_at_all`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_run_killed_after_the_owner_turn_does_not_run_it_again`

The flow resolves its workspace once because no story exists at setup time. Each iteration then
draws without changing the register, creates the `fixes` story bucket when needed, and guards the
seeded story file before any agent turn. Only repositories with paths reported by `changed_files`
are gated and committed; repositories merely listed in the workspace manifest are ignored.

The stages, in order: [draw-and-seed](#draw-and-seed), [own-the-item](#own-the-item), [gates](#gates), [operator-block](#operator-block), [document](#document), [commit-and-redraw](#commit-and-redraw).

The flow starts when the workspace directories resolve before a record is drawn; or when the register holds an open `qa` record of a workspace repository.
It ends in one of these ways: a register with no open `qa` record of the workspace returns `Done` without starting another item; an item whose commit landed closes its record as `done` and draws the next; an item no repository landed a commit for leaves its record open and returns `Done`; a fix that changed nothing raises `WorkflowFailed` and leaves its record open; an owner turn that reports a block waits for an operator; an exhausted gate-repair budget waits for an operator.

## Steps

### draw-and-seed

- kind: seed

`setup` resolves the workspace directories. `start` draws the oldest open `qa` record of the
workspace repositories. A dry draw returns `Done`. Otherwise `start` records what was already
dirty, seeds the record as a one-criterion story whose Context names the record, prepares its
story paths, checks that the story file is readable, and records the owner's baseline before
`work` begins.

### own-the-item

- kind: run

`work` renders `fix-item` with the record's summary, story paths, epic identity, the operator's
last answer, and the previous lap's gate report. The owner plans, writes the repair, and QAs it in
one high-power session. A blocked result goes to the block path.

### gates

- kind: verify

`check` calls `render_gate` (defined at `workflows/src/workhorse_workflows/coder/fix/flow.py::render_gate`) to format each gate failure report. It asks every changed repository to run each gate in `GATE_ORDER`, using the repository's own
`make <gate>` fallback when no service-specific command is configured. Clean or skipped gates pass.
A dirty gate produces a `FailureReport`. The check then lists the paths the turn changed and did
not commit, minus the paths dirty at the owner baseline. While laps remain, the reports re-enter
`work`, and the still-red final lap enters the block path with the failure output preserved.

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

The flow hands the seeded story to `Docs` with the epic, the target environment and the paths that
were dirty before the item began. `passed` and `not_applicable` permit continuation. Any other
documentation result raises `WorkflowFailed`, so an item whose book entry failed is never
committed or closed.

### commit-and-redraw

- kind: run

`commit` commits the changed repositories with `kind="fix"`, the story identity, and no push or
pull request. A fix that changed nothing has no commit carrying the story's trailer, so the commit
raises `WorkflowFailed` and the record stays open. The flow then reads the HEAD of every workspace
repository that holds a commit of the item. With none, the record stays open and the run returns
`Done` with that reason. Otherwise the flow closes the record as `done`, naming each repository and
its short commit, and returns to `start`. Each drained item gets its own commit, and the next draw
is made only after the current record is closed.
