---
type: concept
slug: coder-qa-package
title: Coder qa package
---
# Coder qa package

The `qa` machine resolves one authored story, rebuilds the QA obligation packet from the
implementation diff, plans and runs the story's QA scenarios, and audits the evidence against
what was promised. It handles product repairs, environment setup repairs, and rescope decisions,
bounded by repair ceilings and repeated failure detection. It is a sub-flow entered by the Coder
main flow after documentation passes, and can also be run directly with `workhorse-coder run qa`.

The flow's verdict routing is delegated to the `RoutedFindings` tuple, which classifies assessment
results into product failures, development-target reports, environment problems, regression
detections, and operator-gated blocks. The checkpointed `QaLoop` carries assessment and audit
records, repair counters, failure fingerprints, and escalation state. Repair budgets are enforced
per defect kind; exhausted budgets or human mode escalate to an operator gate.

- code: `workflows/src/workhorse_workflows/coder/qa/flow.py`
- code: `workflows/src/workhorse_workflows/coder/qa/flow.py::Qa`
- code: `workflows/src/workhorse_workflows/coder/qa/flow.py::RoutedFindings`
- code: `workflows/tests/coder/qa/test_flow.py::docs`
- code: `workflows/tests/coder/qa/test_flow.py::ostler`
- code: `workflows/tests/coder/qa/test_flow.py::web`
- code: `workflows/tests/coder/qa/test_flow.py::test_human_operator_modes_wait_on_the_story_context_file`
- code: `workflows/tests/coder/qa/test_flow.py::test_a_resolver_that_grounds_its_answer_settles_a_qa_block.never`
- code: `workflows/tests/coder/qa/test_flow.py::test_a_turn_that_says_it_cannot_proceed_reaches_the_operator`
- tests: `workflows/tests/coder/qa/test_flow.py`
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_through_every_gate`
- detail: [coder QA subflow](coder-qa-subflow.md)

The `qa` flow runs against a docs repository, an opt-in workspace of code repositories, and the QA
process-edge itself, all of which the QA test fixtures stand up: `docs` builds a docs repo
carrying one epic with its `## Stories` listing, one built story carrying an `Implementation
Status: Done` line, the runbook under `docs/features/app/ops/`, and the dev-phase plan decoded
into `plan-context.json` under `docs/specs/<story>/` — exactly the artifacts the production
context gate rebuilds against. `ostler` installs a scripted `_Ostler` (with its `_Session`
subclass of the real `Ostler` facade) at the QA process edge in `okf`, `qa`, and `evidence`
node modules, scripting `qa_context`, `qa_context_validate`, `qa_validate`, `qa_run`, and
`artifact_vet`, and writing the artifacts a real runner writes so the evidence gate reads
evidence rather than being told about it. `web` stands up a real `web-app` git repo whose
`agents.yml` declares a `regression:` command — the seam regression selection reads, decoupled
from stack type.

The QA flow's gate-and-resolver behaviour is asserted against three parameterised tests on the
operator-resolution seam. `test_human_operator_modes_wait_on_the_story_context_file` proves
both the canonical `human` and the legacy `operator` modes block on `<story>/context.md`
without spending a resolver turn. The `never` callback inside
`test_a_resolver_that_grounds_its_answer_settles_a_qa_block` asserts an `answered` arm
produced by the resolver must not park the run on the context file — a grounded answer is
consumed at the same point a human's would be. `test_a_turn_that_says_it_cannot_proceed_reaches_the_operator`
proves every binding turn on the clean path can refuse and the refusal reaches the operator
instead of being retried at the same turn.

## Methods

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: combines run labels with telemetry labels for the `qa` machine
- does: emits every budget counter from the carried `QaLoop` under the `qa.` prefix, including counters still at zero, so the absence of a label (not a zero) is what distinguishes a never-spent budget from a spent one
- does: emits assessment and audit dimensions as verdict-group labels under the `qa.` prefix
- does: returns the base run labels alone when no `QaLoop` is present in the state, so `start` and `setup` (which run before any loop exists) report no counters or verdicts
- returns: returns labels used for state telemetry
- verify: count(subject="qa state label sets", equals=1)
- code: `workflows/src/workhorse_workflows/coder/qa/flow.py::Qa.state_labels`
- tests: `workflows/tests/coder/test_telemetry.py::test_qa_reports_every_budget_on_its_loop`
- tests: `workflows/tests/coder/test_telemetry.py::test_a_state_with_no_loop_yet_reports_only_the_base_labels`

