---
type: flow
slug: okf-book-exercise
title: okf-book exercise run
---
# okf-book exercise run

The `ExerciseBook` sub-flow compiles one surface's book into scenarios, brings the app's stack up
or adopts one already serving, and runs every scenario against it. It is entered by the
[check-okf-book flow](check-okf-book.md) after a book checks clean, and by the writer's own
`exercise` command between turns through the same compile-and-run code.

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-okf-book.dot")
- steps:
  - [run](../workhorse-okf-book.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [check-okf-book flow](check-okf-book.md)
- detail: [okf-book write turn](okf-book-write.md)
- tests: `workflows/tests/okf_book/main/test_exercise_book_flow.py::test_a_compiled_book_runs_against_the_stack_it_brings_up`

The stages, in order: [compile](#compile), [bring-up](#bring-up), [run](#run).

The flow starts when it is handed a service whose book is checked clean and a source repository to
read its runbooks from.
It ends in one of these ways: the book compiles to no plan and the run fails with the reason it has
none; the app's stack cannot come up and the run fails with the stack's notes; every scenario runs
and the result carries each failing check, or passes.

The implementation is `workflows/src/workhorse_workflows/okf_book/main/exercise_book_flow.py::ExerciseBook`.

- code: `workflows/src/workhorse_workflows/okf_book/main/exercise_book_flow.py::ExerciseBook` @d46c9a338979

## Steps

### compile

- kind: prepare

`start` compiles the service's book into a plan of scenarios. A book that compiles to no plan ends
the run immediately, with the reason read off the book's own gaps.

- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::compile_scenarios` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::CompileOutcome` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::unplanned_problem` @24e231d223b0

### bring-up

- kind: health

`bring_up_stack` brings the app's stack up, or adopts one already serving. A stack that cannot
come up stops the scenarios and records the stack's own notes as the failure, rather than
attempting to run scenarios with nothing to run them against.

- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::bring_up` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::StackReadiness` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::stack_down_result` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::book_runbooks` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/local_calls.py::Runbook` @6c72a0b6848e

### run

- kind: run

`run_scenarios` runs every scenario against the stack, on a copy of the app when the stack serves
nothing of its own. A server gone before the first scenario runs is brought up once more; a
resumed run gets that once-more again, since the process before it stopped the server on its way
out. The stack bring-up started is released whatever the run's outcome.

- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::run_plan` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::release` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::copy_env` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_run.py::with_app_logs` @24e231d223b0
- code: `workflows/src/workhorse_workflows/okf_book/shared/blueprint.py::blueprint` @171a2bbd19a0
