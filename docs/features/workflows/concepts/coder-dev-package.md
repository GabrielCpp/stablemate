---
type: concept
slug: coder-dev-package
title: Coder dev package
---
# Coder dev package

The `dev` machine plans one story, validates each service layer in the plan against the service's
declared gates, and repairs implementation changes when a gate does not pass. It is a sub-flow
entered by the Coder main flow when a story is ready for implementation, and can also be run
directly with `workhorse-coder run dev`.

The flow chains planning prompts (plan, replan-with-answer) with per-layer implementation
dispatching and gate validation. Each layer is selected from the plan, implemented by an agent
turn, and tested against the layer's declared repository gates. Failed gates offer an automatic
resolver a bounded repair budget; exhausted repairs or human mode escalate to an operator gate.

- code: `workflows/src/workhorse_workflows/coder/dev/flow.py`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev`
- tests: `workflows/tests/coder/test_dev.py`
- detail: [coder dev nodes](coder-dev-nodes.md)

