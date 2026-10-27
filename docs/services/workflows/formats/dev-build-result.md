---
type: format
slug: dev-build-result
title: Coder development build result
---
# Coder development build result

The dev owner replies with this claim at the end of the build phase. It says the plan is built
and every declared gate ran green, and it lists every change the build made to the plan.

- file: none, agent reply and checkpoint value
- config: `BuildResult` build phase output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::BuildResult` @4ed65104b9b1
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)
- detail: [coder dev-build prompt](coder-dev-build-prompt.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_fresh_story_runs_plan_build_and_review_in_that_order`

## Fields

### status
- type: literal `ready` or `blocked`
- required: true
- semantics: `ready` when the plan is built, committed and green on every declared gate, `blocked` when only the operator can decide
- verify: json_path(path="$.status", matches="ready|blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::BuildResult.status` @4ed65104b9b1

### notes
- type: `str`
- default: empty string
- required: false
- semantics: what the owner built and ran green, or on `blocked` the one question that would unblock it
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::BuildResult.notes` @4ed65104b9b1

### follow_ups
- type: list of follow-up entries, as the [development story result](dev-story-result.md#follow_ups) defines them
- default: empty list
- required: false
- semantics: product work the working slice does not need, filed as `coder` records on the debt register instead of done on the side
- verify: json_path(path="$.follow_ups", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::BuildResult.follow_ups` @4ed65104b9b1
- detail: [coder backlog contract](../concepts/coder-backlog-contract.md)

### departures
- type: list of departure entries, each with `change`, `reason` and `advice`
- default: empty list
- required: false
- semantics: every change the build made to the plan, empty when the build followed the plan as written
- verify: json_path(path="$.departures", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::BuildResult.departures` @4ed65104b9b1
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Departure` @4ed65104b9b1
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_departure_without_advice_sends_the_build_back_when_an_advisor_is_offered`
- tests: `workflows/tests/coder/dev/test_flow.py::test_without_an_advisor_a_departure_passes_and_every_phase_runs_at_max`

Each departure carries three keys. `change` says what the build does differently from the plan
and where `plan.md` now records it. `reason` says why building the plan as written would fail a
criterion or a gate. `advice` holds the advisor's answer as given, and why the build did not
follow it if it did not. `advice` may be empty only when the turn is offered no advisor. When an
advisor is offered, the flow sends a departure with empty `advice` back to the build.
