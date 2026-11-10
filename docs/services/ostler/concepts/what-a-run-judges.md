---
type: concept
slug: what-a-run-judges
title: What a run judges
---
# What a run judges

`ostler book run` judges whether the live service does what the [service book](service-book.md) says. It judges three things, each against the model, and a fourth report says how much of the book the run saw.

- Journeys: each step is taken on the model and on the service. The step passes when both answer alike and the rows the watch reads afterwards are equal.
- Cells: each cell of each lifecycle matrix arranges its scene on the service, takes one action there and compares the model and the service the same way.
- Input classes: each endpoint's inputs are varied one at a time, from a call the run already saw succeed. A class is one way to fill one input, a valid one the shape names or a wrong one the shape implies. The model says what a class gets when it has a rule for it. When it has none and the class is wrong, the service's declared default refusal is expected.
- The witness lists each declared answer and each declared field the run never saw the service produce.

A run leaves with 0 when all of this passes, 1 when the service or the book is wrong, 2 when the command cannot do what was asked and 3 when the place cannot be judged. A run of some journeys only, or of some endpoints, does not fail for what it left unseen, but an unmet declared divergence of a named endpoint still fails it.

Before it plays anything, the run reads each health journey. It stops with exit 3 and `could not judge: <why>` when a host does not answer, when a gateway answers 502, 503 or 504 the book does not declare, or when a health journey fails. What ran before the stop is no verdict.

- rule: a run refuses to judge an unhealthy environment, so a service that is down never turns the book red
- rule: a health journey is judged against the model like any other journey, so it changes when the standing world changes
- rule: a gap the book can close by arranging a state, a caller or an input is closed, and only what lies out of the book's reach is declared `Unseen` with a `Because` and a why
- rule: an answer or field no run saw and no `Unseen` declares fails a full run, and so does an `Unseen` for something the run did see
- rule: a declared input class the service now refuses fails the run, because the divergence is gone and its declaration is stale
- rule: a wire that types its fields plays no wrong type, no value outside an enum and no null, because such a value never reaches the service
- rule: a failure is the book wrong or the service wrong, and the fix never loosens a shape or widens a fixture to make a run green
- code: ostler/ostler/book/cli.py::cmd_run@80afbf8ae3c7
- code: ostler/ostler/book/cli.py::unhealthy@a5cb92003bb1
- code: ostler/ostler/book/runner.py::walk@65ef938bcb5d
- code: ostler/ostler/book/runner.py::agree@cd74b3fc30a6
- code: ostler/ostler/book/cells.py::play@002f27654e76
- code: ostler/ostler/book/inputs.py::play@a35750c5423f
- code: ostler/ostler/book/inputs.py::Diverges@715904303028
- code: ostler/ostler/book/witness.py::Unseen@8032062e8dcd
- code: ostler/ostler/book/witness.py::WitnessReport@bc2d28ac2287
- tests: ostler/tests/test_book_todo.py::test_run_plays_the_journeys_the_cells_and_the_input_classes
- tests: ostler/tests/test_book_inputs.py::test_a_typed_wire_plays_no_wrong_type_no_out_of_enum_and_no_null
- tests: ostler/tests/test_book_inputs.py::test_a_declared_divergence_needs_no_default_refusal
- tests: ostler/tests/test_book_witness.py::test_unseen_refuses_a_blank_why
