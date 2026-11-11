---
type: concept
slug: coder-book-qa-package
title: Coder book qa package
---
# Coder book qa package

The `book_qa` package is the book lane of the Coder workflow. A story that touches a service with an
executable book has that service judged by a run of the book, and the lane costs one seat turn. The
verdict costs no model call. The lane is its own flow with the same result type the scenario QA
returns, so the Coder main flow reads a verdict from it and never its inside. A story with no covered
service passes the lane with no agent call and no stack.

Five parts share the work. Coverage answers which of the story's services have an executable book,
and never knows how a book is played. The seat owns the book's change for one story and the claims the
app does not meet, and never knows the verdict. The judgement plays the touched calls and routes the
outcome, and never knows how the book was edited. The running copy is a copy of the stack that runs the
story's code, and never knows the book. The record lands the book's change beside the story's code and
writes the calls a passed check played.

The lane shares its story params, labels, owner session, stack release, lap budget and operator block path with the scenario QA through one base, `QaOwner`, so a change to how a QA lane parks or labels itself lands in one place for both.

The flow is [Coder book QA flow](../flows/coder-book-qa.md). The seat's reply is the
[book QA owner result](../formats/book-qa-owner-result.md), and the lane's memory is the
[book QA record](../formats/book-qa-record.md). The lane sits ahead of the scenario lane in the
[coder lane order](coder-lane-order.md).

- code: `workflows/src/workhorse_workflows/coder/shared/qa_owner.py::QaOwner` @7c46741d5c85
- code: `workflows/src/workhorse_workflows/coder/book_qa/flow.py::BookQa` @9bef23bc81f1
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::covered_services` @5794657c4d83
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::book_check` @08d492ed6b13
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::book_run` @a32cf444c3c3
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::commit_service_book` @c3c45d5dacbc
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::CoveredServices` @3f5d80c4d178
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookPlay` @d4b8c52a4eaa
- code: `workflows/src/workhorse_workflows/coder/shared/story_commit.py::uncommitted_paths` @7f13eae9cb98
- code: `workflows/src/workhorse_workflows/coder/shared/roles.py::ROLES` @af527f9dd67b
- rule: a run that could not judge, exit 3 of the book tool, never becomes a finding for the developer, because an environment that is not healthy is the operator's
- rule: a story does not pass the lane while the seat reports a finding, even when the run is green, because a declared defect makes the run green by design
- rule: the seat's edits stay inside `services/<name>/` of the covered services, and the lane commits only paths there and refuses the commit on any other product path the seat left
- rule: the lane ends in a pass, a hand-back to the developer or a question to the operator, and a spent lap budget is a question to the operator
- rule: the seat names the calls the judgement plays, and the judgement refuses a covered service whose list is empty, so the plays never fall back on the book's stale list
- rule: the verdict is a plain command over the book tool's exit code, so the seat's turn is the only model spend of the lane
- rule: a claim the app does not meet stays in the book as the intent with the app's answer declared as a known defect, and the seat also returns it as a finding
- rule: the seat reads the story, its plan and its review answers, then the diff, and never another QA's plan, report or evidence
- rule: the base is played before the seat edits, and a red base or an unhealthy environment makes the seat report `blocked` and repair nothing
- rule: the run plays the calls the story touches, not the whole book
- rule: the book reaches the stack copy the run leased without naming it, because the play takes the lease as `--copy` and the book names a host as the run's copy
- rule: a covered service stays judged by the scenario lane too until its compiled scenarios are dropped, so the lanes run one after the other and a story that holds both kinds pays for both
- rule: the lane depends on the result type of the scenario QA and not on its inside, so a third lane is one more flow and one more branch in the main flow
- rule: a second visit for the same story replays the calls the first visit recorded and calls the seat only when that play disagrees, and the findings recorded beside them still stand while the replay is green
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_story_with_no_covered_service_passes_with_no_seat_and_no_stack`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_run_that_could_not_judge_asks_the_operator_and_spends_no_second_turn`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_finding_beside_a_green_run_goes_back_to_the_developer_and_the_book_still_lands`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_product_edit_outside_the_book_is_refused_and_sent_back_unlanded`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_run_that_stays_red_parks_at_the_operator_after_the_lap_budget`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_seat_that_names_no_call_for_a_covered_service_is_sent_back_before_any_play`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_second_visit_replays_the_recorded_calls_with_no_seat`
- detail: [coder book QA flow](../flows/coder-book-qa.md)
- detail: [coder lane order](coder-lane-order.md)

## Methods

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: combines the story's run labels with the `book-qa.` budget counters carried in the next state's parameters
- does: reports the `laps` and `blocks` counters under the `book-qa.` prefix, so the absence of a label distinguishes a never-spent budget from a spent one
- returns: labels used for state telemetry
- verify: count(subject="book-qa state label sets", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/qa_owner.py::QaOwner.state_labels` @80ca7c994dac
