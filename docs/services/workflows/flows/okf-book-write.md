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

- code: `workflows/src/workhorse_workflows/okf_book/main/write_book_flow.py::WriteBook` @6fdc237dbe80

## Steps

### start

- kind: prepare

`start` snapshots the tree before the writer's turn runs, so anything it changes outside its book
folder can be put back after. `reset_command_state` then writes the state file the writer's three
commands read, with none of their runs spent.

- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::snapshot` @d458a2a86e0b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::WriterCommandState` @6ebfece6cfd3
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::write_command_state` @34d19133a0d6
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_jobs.py::settle_jobs` @cb4daf02dd0f

### write

- kind: drive

One high-power turn, confined to its book folder, opens on the gates the book last failed and
writes until its own check and run both pass, or a turn's steps run out. The turn resumes the
owner's conversation across laps; a turn that ends without a reply starts the next one fresh. The
turn's three commands are built once per turn and share the run cap.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_request.py::writer_request` @bef0a0f414e4
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_request.py::offered_qa_tools` @6a0ce53f33cd
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/turn_budget.py::WRITER_STEPS` @26493bed070e
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/owner_gate.py::gate_template_args` @b5e05dad8192
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/source_view.py::turn_folder` @ea41991b48ca

### record

- kind: run

`record_writer_turn` records what the turn cost and the side it named of each group the gates
showed it. A turn that named the book's side of a group and changed no page starts its next
conversation fresh, so it is not shown the same gate again with nothing new to say about it.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/owner_gate.py::record_owner_reply` @f794ff17e1eb
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/operator_answer.py::mark_heard` @126f9adf3829
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/operator_answer.py::forget_heard` @5bed96769ea4
- code: `workflows/src/workhorse_workflows/okf_book/shared/metrics.py::turn_metric` @a975c03cfa0b
- code: `workflows/src/workhorse_workflows/okf_book/shared/metrics.py::record_turn` @dcb0e0f9ba56

### put-back

- kind: run

`put_back` restores every path outside the book folder the turn changed, whether the turn
committed pages, failed, or ran out of steps, because the writer may write only under its own
book.

- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::book_changes` @fca5469ace05
- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::put_back_outside` @f4cf389d31f1
- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::kept_changes` @3ec121477ec9

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

- code: `workflows/src/workhorse_workflows/okf_book/shared/book_commits.py::book_commit_subject` @9d2f6ac9caa4
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_commits.py::unfinished_book_commit_subject` @d5e9fc5d23fe
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_links.py::in_book` @8d03894000e1

## The writer's three commands

The owner's turn may run only `writer_ostler`, `check_pages` and `exercise`, each invoked against
the state file `write_book` wrote. Every run of `check_pages` or `exercise` spends one of a shared
80-run budget for the turn; `writer_ostler` spends its own, smaller budget.

A call that comes back before its run finishes tells the writer to make the same call again. That
next call reads the result without spending a run. The result stays readable while no page has
changed since its run started. A page written after the run started makes the result read once,
and the call after that starts a new run on the edited book.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::CHECK_AND_SCENARIO_RUN_CAP` @9a134c1e412b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::spend_check_or_scenario_run` @52b81804e7dc
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::spend_ostler_run` @13e19c025a0b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_commands.py::run_quietly` @91e51df61ba0
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_jobs.py::run_or_attach` @b34e5584bd08
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_jobs.py::detached` @893b45698765

`check_pages` prints every problem the turn's own pages, or named sections of them, still hold,
once the problems the book already held at the turn's start and that the turn did not touch are
set aside, or prints `No problems`.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/check_pages.py::scoped_problems` @c1f3dd8f7cbb
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/check_pages.py::checked` @0baf9df67576
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/page_sections.py::page_sections` @fd939b0afc15
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/page_sections.py::PageSections` @2e2be4e16202

`exercise` runs the book, or the pages and fixture pages it is named, against the real app, and
prints every failing check or `All N scenarios pass`. It keeps the app's stack up across the
turn's checks through a file lock, so two runs of the writer's commands never fight over the same
app. A failing run keeps the runner's screenshots, command logs and junit files in a stamped folder under the run's `evidence/` folder, the newest 20, and prints that folder's path first as an `evidence:` line.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/exercise.py::exercise_book` @66e969a64dd3
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/exercise.py::exercised` @4d3cb75a3028
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/exercise.py::keep_evidence` @b580da2a302d
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_stack.py::KeptStack` @c018b2c70b59
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_stack.py::runbooks_digest` @90248933af5c

`writer_ostler` runs `scaffold`, `fmt`, a `gc` held to the surface's own book, and a `relink` of
other books' links into it; `gc --write` deletes the pages the book's entries page does not reach.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_ostler.py::run_ostler` @0716c841fd60
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_ostler.py::_collect_garbage` @7e67e61344c7
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_ostler.py::_relink` @16aa6d09bab3
