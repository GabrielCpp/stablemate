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
