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

The stages, in order: [preflight](#preflight), [route](#route), [reground](#reground), [copy-source](#copy-source), [write](#write), [check](#check), [run](#run), [settle-run](#settle-run), [map-failures](#map-failures), [report](#report), [gate](#gate).

The flow starts when the run is given at least one surface, each naming a service, a kind and an entry; it fails before any turn when none is given.
Before the first turn it renders the repo's agent files and brings each declared stack up once, so a setup failure waits for the operator at the start of the run.
It ends in one of these ways: every surface's book checks clean and passes its run, and the run reports with no blocker; a blocker stops the run at an operator gate, whose answer the run settles itself, closing what now passes and sending the rest back to its owner.

The implementation is `workflows/src/workhorse_workflows/okf_book/main/flow.py::OkfBook`.

- code: `workflows/src/workhorse_workflows/okf_book/main/flow.py::OkfBook` @de9f4c940fbc

## Steps

### preflight

- kind: run

`start` checks the run's setup before any owner turn. It renders the repo's agent files, and a render
that fails waits at an operator gate until the answer renders them again. It then brings up the stack
each existing book declares and releases it at once. A surface with no book folder yet, or whose book
declares no stack, is skipped. A stack that does not come up waits at the `preflight-gate.md` gate,
whose text names the service and the stack's notes. The operator fixes the stack and answers, and the
check runs again.

- code: `workflows/src/workhorse_workflows/okf_book/main/flow.py::OkfBook` @de9f4c940fbc
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/preflight.py::down_stack` @205895c7b25b

### route

- kind: run

`route_book` decides what a surface's book needs next: a missing book is sent to be written, a book
citing a changed file is reground first, a book the last gate left failures for is repaired, and a
book with no problem that this run did not write goes straight to its run. Each surface the run
names is routed through its own book folder.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/surface.py::Surface` @f4701f9ede8b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/surface_pass.py::write_pass` @e71955962c44
- code: `workflows/src/workhorse_workflows/okf_book/shared/citations.py::cites_changed_file` @8fa526787055
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_commits.py::book_commit_subject` @9d2f6ac9caa4
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

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/source_view.py::build_source_view` @4b30f3b91943
- code: `workflows/src/workhorse_workflows/okf_book/shared/source_repo.py::source_repo` @f10fc15c4567

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

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/book_problems.py::book_problems` @659c155d19b6
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/check_lead.py::unheld` @1216ce09768b
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/check_lead.py::record_check` @ab29e0dc54f4
- code: `workflows/src/workhorse_workflows/okf_book/shared/page_check.py::page_problems` @a8db22322976
- code: `workflows/src/workhorse_workflows/okf_book/shared/page_check.py::PageProblem` @18046d49ead7
- code: `workflows/src/workhorse_workflows/okf_book/shared/source_coverage.py::uncited_by_folder` @7f14eaf78858
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_compilation.py::obligation_page` @fa2f092b6c61

### run

- kind: run

`run_book` hands the checked book to the [okf-book exercise run](okf-book-exercise.md), which
compiles it to scenarios and runs them against the real app.

- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::ExerciseResult` @6cb198524f89

### settle-run

- kind: verify

`settle_run` reads what the run did. A run the runner itself stopped measured nothing and is a
blocker on the runner, not a lap. A passing book is done. Each failure the book's owner has already
named another side's becomes a blocker on that side, one per signature, with the command that
reruns only its checks. A stack that cannot come up is routed to the runbook its owner can repair.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/gate.py::block_stopped_runner` @c13f2b976ffa
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/gate.py::rerun_command` @197891c49978
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/lead_findings.py::service_findings` @93af96c7d7b1
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/lead_findings.py::attributed` @06ef97a4b356
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/progress_ledger.py::record_lap` @6dcdab9913d1
- code: `workflows/src/workhorse_workflows/okf_book/shared/blockers.py::record_blocker` @bacaac0c7700

### map-failures

- kind: run

`map_run_failures` maps each failure the owner can still fix to the page that covers it, and sends
the book back for another repair turn, since a claim the run cannot exercise is a defect of the
book and not of the run. A lap that did not lower the book's failed checks stops the laps and
blocks instead of repeating.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/lead_findings.py::with_instructions` @b51fa8c923bc
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/progress_ledger.py::stalled` @32c3f4ebabed
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/progress_ledger.py::trend` @2b7dd74899ed
- code: `workflows/src/workhorse_workflows/okf_book/shared/scenarios.py::plan_scenarios` @fb19470d0287
- code: `workflows/src/workhorse_workflows/okf_book/shared/production.py::entry_pages` @cc91dc79469c
- code: `workflows/src/workhorse_workflows/okf_book/shared/imports.py::reached_files` @e312ac08da10
- code: `workflows/src/workhorse_workflows/okf_book/shared/stack.py::stack_files` @73e6d6f9ba2c

### report

- kind: run

`report` publishes the run's account of every surface: what each turn cost, each page nothing
reaches, and the gaps the run could not close. With no blocker left the run is done.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/report.py::build_report` @fd4a91d5d2d1
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/claim_snapshot.py::book_claims` @9d73d4d3be79

### gate

- kind: drive

A blocker stops the run at an operator gate naming each one, its cause, its pages and the command
that reruns only its checks. `resume` keeps the operator's answer for the next owner turn to read.
`settle_gate` reruns each blocker's checks against the answer: a claim the answer changed is a
finding for its page's writer, and `route_blocked` sends only the books the gate's settlement still
names back through [route](#route).

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/gate.py::open_gate` @7db2b8749092
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/gate.py::settle_gate` @bf3dd431de8e
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/claim_snapshot.py::changed_claims` @57a8620d5f3a
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/operator_answer.py::answer_below` @73a08a138358
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/operator_answer.py::write_answer` @88058a978352
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_flow.py::BookFlow` @04fac76d75ef
