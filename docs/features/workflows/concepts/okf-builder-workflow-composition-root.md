---
type: concept
slug: okf-builder-workflow-composition-root
title: OKF-builder workflow composition root
---
# OKF-builder workflow composition root

The `workhorse-okf-builder` console script imports this module and calls `main`. Its `workflow`
registry is the OKF-builder distribution's composition boundary: a bare run starts the
code-to-book build machine, while the named `walkthrough-web` flow independently walks a
previously built web book.

The registry is rooted at `workhorse_workflows.okf_builder`, rather than the default-flow
subpackage, so prompt paths and repository-flavor lookup resolve from the package containing both
machines. It registers the one shared node blueprint and the web walkthrough flow. In dry-run
mode, it supplies replies that allow surface enumeration, investigation, coverage recheck, and
web walkthrough gates to advance; omitted worklists and discoveries therefore converge without an
agent turn.

`main` adapts the default entry point in that registry into the callable required by the installed
console script. The module re-exports the default flow and its convergence limits so embedding and
test callers use the same registry contract as the command.

- code: `workflows/src/workhorse_workflows/okf_builder/workflow.py::workflow`
- code: `workflows/src/workhorse_workflows/okf_builder/workflow.py::main`
- code: `workflows/src/workhorse_workflows/okf_builder/workflow.py::__all__`
- detail: [OKF-builder audit flow](../flows/okf-builder-audit.md)
- detail: [OKF-builder web walkthrough flow](../flows/walkthrough-web.md)
- detail: [OKF-builder shared blueprint](okf-builder-shared-blueprint.md)
- detail: [OKF-builder shared schemas](okf-builder-shared-schemas.md)
- detail: [OKF-builder shared paths](okf-builder-shared-paths.md)
- detail: [OKF-builder workflow entry point](okf-builder-workflow-entry-point.md)
- detail: [OKF-builder main build machine](okf-builder-main-build-machine.md)
- detail: [OKF-builder checkpoint gate](okf-builder-shared-checkpoint.md)
- detail: [OKF-builder shared stubs](okf-builder-shared-stubs.md)
- detail: [OKF-builder shared vocabulary](okf-builder-shared-vocabulary.md)
- detail: [OKF-builder shared worklist](okf-builder-shared-worklist.md)
- detail: [workflow kit export surface](workflow-kit-export-surface.md)

## Exports

### MAX_RESCAN_ROUNDS
- type: `int`
- default: `6`
- required: true
- semantics: maximum number of coverage re-scans before the run blocks on the operator gate when a clean doctor output is not converging
- verify: count(subject="OKF-builder coverage rescan round cap", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::MAX_RESCAN_ROUNDS`

### MAX_STALL_ROUNDS
- type: `int`
- default: `3`
- required: true
- semantics: maximum number of consecutive rounds an unchanged doctor finding set is tolerated before the run blocks on the operator gate
- verify: count(subject="OKF-builder stall round cap", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::MAX_STALL_ROUNDS`

### OkfBuilder
- type: class
- required: true
- semantics: the default state machine that turns service source into a complete OKF book; used as the entry point for a bare `run` command
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder`
- detail: [OKF-builder main build machine](okf-builder-main-build-machine.md)

### Audit
- type: class
- required: true
- semantics: the standalone read-only semantic review flow registered as the named `audit` machine, assessing explicitly selected source against the current book, prompting the reviewer agent for verdicts, and returning a report without mutating the book
- code: `workflows/src/workhorse_workflows/okf_builder/audit/flow.py::Audit`
- detail: [OKF-builder audit workflow](../flows/okf-builder-audit.md)

### WalkthroughWeb
- type: class
- required: true
- semantics: the web walkthrough sub-graph registered as the named `walkthrough-web` machine, proving a built OKF book against a running application
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb`
- detail: [OKF-builder web walkthrough](okf-builder-web-walkthrough.md)
