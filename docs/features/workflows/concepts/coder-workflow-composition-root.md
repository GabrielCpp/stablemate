---
type: concept
slug: coder-workflow-composition-root
title: Coder workflow composition root
---
# Coder workflow composition root

The `workhorse-coder` console script imports this module and calls `main`. Its registry is the
single catalogue of Coder machines: a bare run enters `Coder`, while a named run selects one
registered flow. The default [Coder flow](../../../../workflows/src/workhorse_workflows/coder/main/flow.py)
coordinates story implementation, independent review, documentation, QA, backlog draining, and
the epic pull-request lifecycle; its complete state-machine contract is the [Coder main flow](../flows/coder-main.md).

The registry is rooted at `workhorse_workflows.coder`, keeping prompt paths and repository flavor
lookup relative to the whole workflow rather than the default `main` subpackage. It contributes
the shared node blueprint and exposes seven named flows: `genesis`, `dev`, `review`, `docs`, `qa`,
`fix`, and `fix_ci`. `genesis` and `fix` can only be entered directly; the main Coder flow hands
off to the other five. The dry-run registry supplies parseable success or resolved replies for
every prompt role so a dry run advances through its gates without an agent backend.

- code: `workflows/src/workhorse_workflows/coder/workflow.py::workflow`
- code: `workflows/src/workhorse_workflows/coder/workflow.py::main`
- code: `workflows/src/workhorse_workflows/coder/workflow.py::__all__`
