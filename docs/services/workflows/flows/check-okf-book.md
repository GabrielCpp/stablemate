---
type: flow
slug: check-okf-book
title: Check workhorse-okf-book
---
# Check workhorse-okf-book

An author confirms the `workhorse-okf-book` command is installed and wired before trusting it with
real work. They read the engine version the script carries, render its state graph, and dry-run
the registered flow so no agent turn is spent.

- fixture: none, because the walk reads the installed command and writes nothing the end state depends on
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-okf-book.dot")
- steps:
  - [version](../workhorse-okf-book.md#version)
  - [dot](../workhorse-okf-book.md#dot)
  - [run](../workhorse-okf-book.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [workhorse-okf-book command](../workhorse-okf-book.md)
- detail: [okf-book write turn](okf-book-write.md)
- detail: [okf-book exercise run](okf-book-exercise.md)
- detail: [okf-book reground pass](okf-book-reground.md)
- tests: `workflows/tests/okf_book/main/test_flow.py::test_a_surface_with_no_book_writes_one_checks_it_and_runs_it`

The stages, in order: [route](#route), [reground](#reground), [copy-source](#copy-source), [write](#write), [check](#check), [run](#run), [settle-run](#settle-run), [map-failures](#map-failures), [report](#report), [gate](#gate).

The flow starts when the run is given at least one surface, each naming a service, a kind and an entry; it fails before any turn when none is given.
It ends in one of these ways: every surface's book checks clean and passes its run, and the run reports with no blocker; a blocker stops the run at an operator gate, whose answer the run settles itself, closing what now passes and sending the rest back to its owner.

The implementation is `workflows/src/workhorse_workflows/okf_book/main/flow.py::OkfBook`.

- code: `workflows/src/workhorse_workflows/okf_book/main/flow.py::OkfBook` @e451bf02692b

## Steps

### route

- kind: run

`route_book` decides what a surface's book needs next: a missing book is sent to be written, a book
citing a changed file is reground first, a book the last gate left failures for is repaired, and a
book with no problem that this run did not write goes straight to its run. Each surface the run
names is routed through its own book folder.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/surface.py::Surface` @d26ce27bae11
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/surface_pass.py::write_pass` @fa18d47b728c
- code: `workflows/src/workhorse_workflows/okf_book/shared/citations.py::cites_changed_file` @ac11e672e516
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_commits.py::book_commit_subject` @4ecb25dbf13a
- code: `workflows/src/workhorse_workflows/okf_book/shared/entries.py::SERVICES_DIR` @e28d5f3a41e6

### reground

- kind: run

A book whose cited code changed since its stamp is handed to the [reground pass](okf-book-reground.md)
before any owner turn reads it, so the owner repairs a page against what the code does now, not
against a stale reading of it.

### copy-source

- kind: prepare

`copy_source` builds the owner's read-only copy of the surface's source folder, and blocks the
surface instead of starting a turn when the entry names no folder of the repository.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/source_view.py::build_source_view` @303f3884bd67
- code: `workflows/src/workhorse_workflows/okf_book/shared/source_repo.py::source_repo` @6e5aa862cb6d

### write

- kind: drive

`write_book` hands the surface to one turn of the [okf-book write turn](okf-book-write.md), with
the gates the last check or run left failing, and `settle_write` blocks a surface whose turn ended
with no page committed.

### check

- kind: verify

`check_book` repeats the page check. A problem a group's owner named another side's is held, so a
person is not asked about what the owner already attributed; every problem still left goes back to
the owner, but only when its count did not fall after a repair, so a lap that made no progress
stops instead of looping.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/book_problems.py::book_problems` @a096926152ce
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/check_lead.py::unheld` @b680dbef7b04
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/check_lead.py::record_check` @b680dbef7b04
- code: `workflows/src/workhorse_workflows/okf_book/shared/page_check.py::page_problems` @f5084a979812
- code: `workflows/src/workhorse_workflows/okf_book/shared/page_check.py::PageProblem` @f5084a979812
- code: `workflows/src/workhorse_workflows/okf_book/shared/source_coverage.py::uncited_by_folder` @0680c8fa41af
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_compilation.py::obligation_page` @c55b3025b98a

### run

- kind: run

`run_book` hands the checked book to the [okf-book exercise run](okf-book-exercise.md), which
compiles it to scenarios and runs them against the real app.

- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::ExerciseResult` @24e231d223b0

### settle-run

- kind: verify

`settle_run` reads what the run did. A run the runner itself stopped measured nothing and is a
blocker on the runner, not a lap. A passing book is done. Each failure the book's owner has already
named another side's becomes a blocker on that side, one per signature, with the command that
reruns only its checks. A stack that cannot come up is routed to the runbook its owner can repair.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/gate.py::block_stopped_runner` @09e93ba23de2
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/gate.py::rerun_command` @09e93ba23de2
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/lead_findings.py::service_findings` @fe7fc4a9dca0
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/lead_findings.py::attributed` @fe7fc4a9dca0
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/progress_ledger.py::record_lap` @48800de01113
- code: `workflows/src/workhorse_workflows/okf_book/shared/blockers.py::record_blocker` @6970e3650e24

### map-failures

- kind: run

`map_run_failures` maps each failure the owner can still fix to the page that covers it, and sends
the book back for another repair turn, since a claim the run cannot exercise is a defect of the
book and not of the run. A lap that did not lower the book's failed checks stops the laps and
blocks instead of repeating.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/lead_findings.py::with_instructions` @fe7fc4a9dca0
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/progress_ledger.py::stalled` @48800de01113
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/progress_ledger.py::trend` @48800de01113
- code: `workflows/src/workhorse_workflows/okf_book/shared/scenarios.py::plan_scenarios` @5d6fe81ad856
- code: `workflows/src/workhorse_workflows/okf_book/shared/production.py::entry_pages` @491b7fde8caf
- code: `workflows/src/workhorse_workflows/okf_book/shared/imports.py::reached_files` @79880870727b
- code: `workflows/src/workhorse_workflows/okf_book/shared/stack.py::stack_files` @78c6be30dd3d

### report

- kind: run

`report` publishes the run's account of every surface: what each turn cost, each page nothing
reaches, and the gaps the run could not close. With no blocker left the run is done.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/report.py::build_report` @3d5d0a2d7044
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/claim_snapshot.py::book_claims` @0226e084679e

### gate

- kind: drive

A blocker stops the run at an operator gate naming each one, its cause, its pages and the command
that reruns only its checks. `resume` keeps the operator's answer for the next owner turn to read.
`settle_gate` reruns each blocker's checks against the answer: a claim the answer changed is a
finding for its page's writer, and `route_blocked` sends only the books the gate's settlement still
names back through [route](#route).

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/gate.py::open_gate` @09e93ba23de2
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/gate.py::settle_gate` @09e93ba23de2
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/claim_snapshot.py::changed_claims` @0226e084679e
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/operator_answer.py::answer_below` @9546720d81ec
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/operator_answer.py::write_answer` @9546720d81ec
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_flow.py::BookFlow` @421c9ea075ca
