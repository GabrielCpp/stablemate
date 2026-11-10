---
type: concept
slug: known-defects
title: Known defects
---
# Known defects

A known defect is a call the service is known to get wrong. The model keeps the intended behaviour. A `Defect` declared on the action beside the rule it breaks names the status and message the service gives instead, with the reason in the product's words. A status under 400 declares a success the service should not give, and its message is then only the defect's name.

A journey step on which a declared defect shows passes as `KNOWN` when the service answers what the defect declares. The run counts it apart from the passes and lists it under `Known defects` with the journeys that met it.

When the service answers what was meant, the defect is gone. The step fails with a note to delete its declaration, and the model takes the change the intended behaviour makes so the steps after it stay honest. A declared defect that no journey, cell or input met fails a full run under `Known defects never met`. A declared input divergence works the same way: an unmet `Diverges` fails the run.

- code: ostler/ostler/book/model.py::Defect@96b792c83feb
- code: ostler/ostler/book/runner.py::flawed@31302b4d5f25
- code: ostler/ostler/book/runner.py::defect_answered@0c67eacc1991
- code: ostler/ostler/book/defects.py::never_met@b3124c8bacfc
- code: ostler/ostler/book/defects.py::section@504610991c82
- rule: a known defect is declared on the action beside the rule it breaks and never as a removed step, so a defect cannot be hidden by deleting the journey that shows it
- rule: a declared defect fails the run once the service stops showing it, so the declaration is removed when the service is fixed
- rule: a defect keeps the intended behaviour in the model, and a call the service answers wrongly is a defect on the action while a whole input class it accepts and the book refuses is a divergence on the endpoint
- rule: a partial run does not fail for a defect it never met
- tests: ostler/tests/test_book_inputs.py::test_a_declared_divergence_needs_no_default_refusal
