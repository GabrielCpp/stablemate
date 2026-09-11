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
- code: `workflows/tests/coder/dev/test_flow.py::docs`
- code: `workflows/tests/coder/dev/test_flow.py::workspace`
- tests: `workflows/tests/coder/dev/test_flow.py`
- detail: [coder dev nodes](coder-dev-nodes.md)

The dev package operates against a docs repository carrying one epic with its `## Stories`
listing and one authored story, and against a workspace file naming the code repositories the
plan dispatches into. The `docs` and `workspace` test fixtures stand those inputs up — `docs`
builds the docs repo, `workspace` builds two real git repositories with a checked-in
`.code-workspace` file carrying relative paths exactly as a project ships one — so the gates the
flow describes run against the same artifacts the YAML engine drove against, with the same files
on disk afterwards.

