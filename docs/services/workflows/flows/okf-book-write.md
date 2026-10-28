---
type: flow
slug: okf-book-write
title: okf-book write turn
---
# okf-book write turn

The `WriteBook` sub-flow sends one turn of a surface's book owner. The owner is confined to its
book folder and to three commands: `writer_ostler`, `check_pages` and `exercise`, each counted
against a shared run budget. The turn reads the gates its book last failed, writes until both
checks pass, and the flow commits what it wrote and puts back anything it changed outside its
book. It is entered only by the [check-okf-book flow](check-okf-book.md).

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-okf-book.dot")
- steps:
  - [run](../workhorse-okf-book.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [check-okf-book flow](check-okf-book.md)
- tests: `workflows/tests/okf_book/main/test_write_prompt.py::test_a_committed_page_stamps_and_commits_the_book`

The stages, in order: [start](#start), [write](#write), [record](#record), [put-back](#put-back), [stamp](#stamp), [commit](#commit).

The flow starts when the main flow hands it a surface, its book and source folders, and the gates
its last check or run left failing.
It ends in one of these ways: the turn commits its book's pages and the flow stamps and commits
them; a turn that ends with no reply, or with no page changed, leaves a `WriteOutcome` the main
flow reads as a blocker on the surface; a refused commit, or a failed render of the repo's agent
files, waits for the operator.

The implementation is `workflows/src/workhorse_workflows/okf_book/main/write_book_flow.py::WriteBook`.

- code: `workflows/src/workhorse_workflows/okf_book/main/write_book_flow.py::WriteBook` @1ed9bda827b2

## Steps

### start

- kind: prepare

`start` snapshots the tree before the writer's turn runs, so anything it changes outside its book
folder can be put back after. `reset_command_state` then writes the state file the writer's three
commands read, with none of their runs spent.

- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::snapshot` @a6b5e7558709
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::WriterCommandState` @9a134c1e412b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::write_command_state` @9a134c1e412b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_jobs.py::settle_jobs` @803c631bf44e

### write

- kind: drive

One high-power turn, confined to its book folder, opens on the gates the book last failed and
writes until its own check and run both pass, or a turn's steps run out. The turn resumes the
owner's conversation across laps; a turn that ends without a reply starts the next one fresh. The
turn's three commands are built once per turn and share the run cap.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_request.py::writer_request` @89b377651f1f
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_request.py::offered_qa_tools` @89b377651f1f
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/turn_budget.py::WRITER_STEPS` @476f15aaa45c
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/owner_gate.py::gate_template_args` @2720452eda51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/source_view.py::turn_folder` @303f3884bd67

### record

- kind: run

`record_writer_turn` records what the turn cost and the side it named of each group the gates
showed it. A turn that named the book's side of a group and changed no page starts its next
conversation fresh, so it is not shown the same gate again with nothing new to say about it.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/owner_gate.py::record_owner_reply` @2720452eda51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/operator_answer.py::mark_heard` @9546720d81ec
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/operator_answer.py::forget_heard` @9546720d81ec
- code: `workflows/src/workhorse_workflows/okf_book/shared/metrics.py::turn_metric` @141af4ec2fee
- code: `workflows/src/workhorse_workflows/okf_book/shared/metrics.py::record_turn` @141af4ec2fee

### put-back

- kind: run

`put_back` restores every path outside the book folder the turn changed, whether the turn
committed pages, failed, or ran out of steps, because the writer may write only under its own
book.

- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::book_changes` @a6b5e7558709
- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::put_back_outside` @a6b5e7558709
- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::kept_changes` @a6b5e7558709

### stamp

- kind: run

`stamp_book` stamps every page the turn changed in its own book against the source it cited; pages
of other books it only retargeted a link on go to the commit unstamped.

### commit

- kind: run

The repo's agent files are rendered before the commit. `commit_book` commits the book's changed
pages under this workflow's own subject, so the next run can tell its book apart from one a person
edited by hand. A refused commit, or a failed render, waits for the operator; a retry after the
commit already landed finds nothing left to commit.

- code: `workflows/src/workhorse_workflows/okf_book/shared/book_commits.py::book_commit_subject` @4ecb25dbf13a
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_commits.py::unfinished_book_commit_subject` @4ecb25dbf13a
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_links.py::in_book` @c3c41202b09b

## The writer's three commands

The owner's turn may run only `writer_ostler`, `check_pages` and `exercise`, each invoked against
the state file `write_book` wrote. Every run of `check_pages` or `exercise` spends one of a shared
80-run budget for the turn; `writer_ostler` spends its own, smaller budget.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::CHECK_AND_SCENARIO_RUN_CAP` @9a134c1e412b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::spend_check_or_scenario_run` @9a134c1e412b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::spend_ostler_run` @9a134c1e412b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::run_quietly` @9a134c1e412b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_jobs.py::run_or_attach` @803c631bf44e
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_jobs.py::detached` @803c631bf44e

`check_pages` prints every problem the turn's own pages, or named sections of them, still hold,
once the problems the book already held at the turn's start and that the turn did not touch are
set aside, or prints `No problems`.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/check_pages.py::scoped_problems` @9e640a91a4ea
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/check_pages.py::checked` @9e640a91a4ea
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/page_sections.py::page_sections` @27f1124e7f14
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/page_sections.py::PageSections` @27f1124e7f14

`exercise` runs the book, or the pages and fixture pages it is named, against the real app, and
prints every failing check or `All N scenarios pass`. It keeps the app's stack up across the
turn's checks through a file lock, so two runs of the writer's commands never fight over the same
app.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/exercise.py::exercise_book` @80c0862a329e
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/exercise.py::exercised` @80c0862a329e
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_stack.py::KeptStack` @9db512e10d98
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_stack.py::runbooks_digest` @9db512e10d98

`writer_ostler` runs `scaffold`, `fmt`, a `gc` held to the surface's own book, and a `relink` of
other books' links into it; `gc --write` deletes the pages the book's entries page does not reach.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_ostler.py::run_ostler` @0de17c2e6893
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_ostler.py::_collect_garbage` @0de17c2e6893
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_ostler.py::_relink` @0de17c2e6893
