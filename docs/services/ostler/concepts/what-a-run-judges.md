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
- Twins: for each valid input the run plays, it sends pairs of valid values that differ along one dimension of the field's wire type, such as the time of day or the offset of a date-time, the case or surrounding spaces of text, the trailing zeros of a number, or the order of a list. It sends a pair only where the model predicts the same outcome for both, each value from a world arranged anew, and compares the service's two answers and the rows the call made, changed or removed in the list the watch reads. A record the world minted apart from the call is on neither side.
- The witness lists each declared answer and each declared field the run never saw the service produce.

A run leaves with 0 when all of this passes, 1 when the service or the book is wrong, 2 when the command cannot do what was asked and 3 when the place cannot be judged. A run of some journeys only, or of some endpoints, does not fail for what it left unseen, but an unmet declared divergence of a named endpoint still fails it.

Before it plays anything, the run reads each health journey. It stops with exit 3 and `could not judge: <why>` when a host does not answer, when a gateway answers 502, 503 or 504 the book does not declare, or when a health journey fails. What ran before the stop is no verdict.

- rule: a run refuses to judge an unhealthy environment, so a service that is down never turns the book red
- rule: a health journey is judged against the model like any other journey, so it changes when the standing world changes
- rule: a gap the book can close by arranging a state, a caller or an input is closed, and only what lies out of the book's reach is declared `Unseen` with a `Because` and a why
- rule: an answer or field no run saw and no `Unseen` declares fails a full run, and so does an `Unseen` for something the run did see
- rule: a declared input class the service now refuses fails the run, because the divergence is gone and its declaration is stale
- rule: a wire that types its fields plays no wrong type, no value outside an enum and no null, because such a value never reaches the service
- rule: a pair of twins the model predicts alike and the service answers apart is `underspecified`, reported in its own section and counted apart, and it fails the run unless the book's register holds it
- rule: a pair is judged only on the answers and on the rows the twinned call made, changed or removed, so two worlds that differ in a record the call never touched leave the pair clean
- rule: the register `services/<name>/UNDERSPECIFIED.md` is the product owner's list of open underspecified fields, one entry per endpoint, field and dimension, with the two values, the two answers and the day first seen
- rule: a run reports a finding the register holds as `known`, counted apart from the underspecified ones, and it does not fail the run
- rule: a run adds a finding to the register only when asked, with `--register` for every finding or `--register-outside` for the findings of endpoints outside the calls named
- rule: an entry whose pair no longer splits fails the run until it is removed, because the owner's answer has become a model change, an `ignores` with the owner's reason or a defect
- rule: a pair of twins the model predicts differently is not sent, because the model already reasons on that dimension
- rule: a field declares the dimensions the product is indifferent to with `ignores` and a why, and the run skips those pairs
- rule: a failure is the book wrong or the service wrong, and the fix never loosens a shape or widens a fixture to make a run green
- code: ostler/ostler/book/cli.py::cmd_run@31f0736b8677
- code: ostler/ostler/book/cli.py::unhealthy@a5cb92003bb1
- code: ostler/ostler/book/runner.py::walk@65ef938bcb5d
- code: ostler/ostler/book/runner.py::agree@cd74b3fc30a6
- code: ostler/ostler/book/cells.py::play@68cf5733c64d
- code: ostler/ostler/book/inputs.py::play@e18f62de8044
- code: ostler/ostler/book/inputs.py::Diverges@715904303028
- code: ostler/ostler/book/inputs.py::weigh@42f2cb78c7f7
- code: ostler/ostler/book/register.py::settle@4b43a8da3b41
- code: ostler/ostler/book/http.py::twins@589c3dff328a
- code: ostler/ostler/book/witness.py::Unseen@8032062e8dcd
- code: ostler/ostler/book/witness.py::WitnessReport@bc2d28ac2287
- tests: ostler/tests/test_book_todo.py::test_run_plays_the_journeys_the_cells_and_the_input_classes
- tests: ostler/tests/test_book_inputs.py::test_a_typed_wire_plays_no_wrong_type_no_out_of_enum_and_no_null
- tests: ostler/tests/test_book_inputs.py::test_a_declared_divergence_needs_no_default_refusal
- tests: ostler/tests/test_book_twins.py::test_a_pair_the_model_treats_alike_and_the_app_splits_is_underspecified
- tests: ostler/tests/test_book_twins.py::test_a_pair_the_model_predicts_differently_is_not_sent
- tests: ostler/tests/test_book_twins.py::test_a_pair_on_a_dimension_the_field_ignores_is_skipped
- tests: ostler/tests/test_book_twins.py::test_two_worlds_that_differ_in_a_record_the_call_never_touched_leave_the_pair_clean
- tests: ostler/tests/test_book_register.py::test_a_finding_the_register_holds_is_known_and_does_not_fail
- tests: ostler/tests/test_book_register.py::test_an_entry_whose_pair_no_longer_splits_is_stale
- tests: ostler/tests/test_book_register.py::test_the_option_registers_only_what_lies_outside_the_named_calls
- tests: ostler/tests/test_book_witness.py::test_unseen_refuses_a_blank_why
