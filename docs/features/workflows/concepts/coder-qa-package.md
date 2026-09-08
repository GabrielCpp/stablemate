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
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_through_every_gate`
- detail: [coder QA subflow](coder-qa-subflow.md)

