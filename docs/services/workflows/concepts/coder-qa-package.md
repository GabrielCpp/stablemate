---
type: concept
slug: coder-qa-package
title: Coder qa package
---
# Coder qa package

The `qa` machine hands one story's QA to a single owner session. The owner plans, runs, audits
and repairs through its subagents, and the flow reruns the plan it leaves and gates its claims.
It is a sub-flow the Coder main flow enters after documentation passes, and `workhorse-coder run
qa` runs it directly.

The flow ends in a `QaFlowResult` that is `passed`, `refix` or `replan`. Repair laps are capped
at `MAX_LAPS` and operator blocks at `MAX_BLOCKS`. A spent cap, or a human operator mode, parks
the run on the story's context file.

- code: `workflows/src/workhorse_workflows/coder/qa/flow.py` @5c125dd4ad41
- code: `workflows/src/workhorse_workflows/coder/qa/flow.py::Qa` @5c125dd4ad41
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_spends_one_owner_turn`
- detail: [coder QA subflow](coder-qa-subflow.md)
- detail: [coder QA flow](../flows/coder-qa.md)

The QA flow's gate-and-resolver behaviour is asserted on the operator-resolution seam.
`test_human_operator_modes_wait_on_the_story_context_file` proves that both `human` and the
legacy `operator` modes wait on `<story>/context.md` without spending a resolver turn.
`test_a_blocked_owner_is_answered_and_resumes_with_the_answer` proves that a grounded answer
resumes the owner's session instead of parking the run.

## Methods

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: combines the story's run labels with the `qa.` budget counters carried in the next state's parameters
- does: reports the `laps` and `blocks` counters under the `qa.` prefix, including counters still at zero, so the absence of a label distinguishes a never-spent budget from a spent one
- does: returns the base run labels alone when the parameters carry no counters
- returns: labels used for state telemetry
- verify: count(subject="qa state label sets", equals=1)
- code: `workflows/src/workhorse_workflows/coder/qa/flow.py::Qa.state_labels` @5c125dd4ad41
- tests: `workflows/tests/coder/test_telemetry.py::test_qa_reports_its_repair_laps_and_its_blocks`
- tests: `workflows/tests/coder/test_telemetry.py::test_a_state_with_no_loop_yet_reports_only_the_base_labels`
