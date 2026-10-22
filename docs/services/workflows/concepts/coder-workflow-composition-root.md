---
type: concept
slug: coder-workflow-composition-root
title: Coder workflow composition root
---
# Coder workflow composition root

The `workhorse-coder` console script imports this module and calls `main`. Its registry is the
single catalogue of Coder machines: a bare run enters `Coder`, while a named run selects one
registered flow. The default [Coder flow](../../../../workflows/src/workhorse_workflows/coder/main/flow.py)
coordinates story implementation, documentation, QA, backlog draining, and
the epic pull-request lifecycle; its complete state-machine contract is the [Coder main flow](../flows/coder-main.md).

The registry is rooted at `workhorse_workflows.coder`, keeping prompt paths and repository flavor
lookup relative to the whole workflow rather than the default `main` subpackage. It contributes
the shared node blueprint and exposes six named flows: `genesis`, `dev`, `docs`, `qa`,
`fix`, and `fix_ci`. Only `genesis` is entered directly; the main Coder flow hands off to the other five. Each result schema declares its own dry-run reply, so a dry run advances through its gates
without an agent backend.

- code: `workflows/src/workhorse_workflows/coder/workflow.py::workflow` @a28e84f788c2
- code: `workflows/src/workhorse_workflows/coder/workflow.py::main` @a28e84f788c2
- code: `workflows/src/workhorse_workflows/coder/workflow.py::__all__` @a28e84f788c2
- detail: [Coder main flow](../flows/coder-main.md)
- detail: [Coder genesis flow](../flows/coder-genesis.md)
- detail: [Coder dev flow](../flows/coder-dev.md)
- detail: [Coder docs flow](../flows/coder-docs.md)
- detail: [Coder QA flow](../flows/coder-qa.md)
- detail: [Coder fix flow](../flows/coder-fix.md)
- detail: [Coder CI remediation flow](../flows/fix-ci-remediation.md)
- detail: [Coder shared blueprint](coder-shared-blueprint.md)
- detail: [Coder shared resolution](coder-shared-resolution.md)
- detail: [Coder shared documentation](coder-shared-documentation.md)
- detail: [Coder entry point view selection](coder-entry-point-view-selection.md)
- detail: [Coder main PR boundary](coder-main-pr-boundary.md)
- detail: [Coder QA subflow](coder-qa-subflow.md)
- detail: [workflow kit export surface](workflow-kit-export-surface.md)
