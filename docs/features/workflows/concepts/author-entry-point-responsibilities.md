---
type: concept
slug: author-entry-point-responsibilities
title: Author entry point responsibilities
---
# Author entry point responsibilities

`main` is the Author distribution's shared console entry point. It adapts the registry's default
`Author` flow to the console-script factory; it does not choose between the registry composition
and command-selection views of that entry point.

Use [Author workflow composition root](author-workflow-composition-root.md) when determining the
registry's blueprints, default flow, named subflows, prompt-root package, or dry-run replies. Use
[workhorse-author command selection](workhorse-author-command-selection.md) when selecting the
console operation: `run` executes a flow, `dot` renders its graph, and `version` reports the engine
version. These views answer different questions about the same entry point, so neither is preferred
or deprecated.

- code: `workflows/src/workhorse_workflows/author/workflow.py::main`
- rule: use the composition-root concept for registry behavior and the command-selection concept for console operation; neither concept supersedes the other
- detail: [author main view selection](author-main-view-selection.md)
