---
type: concept
slug: coder-entry-point-responsibilities
title: Coder entry point responsibilities
---
# Coder entry point responsibilities

`main` is the Coder distribution's shared console entry point. It adapts the registry's default
`Coder` flow to the console-script factory; it does not choose between the registry composition
and command-selection views of that entry point.

Use [Coder workflow composition root](coder-workflow-composition-root.md) when determining the
registry's blueprints, default flow, named subflows, prompt-root package, or dry-run replies. Use
[Coder command selection](coder-command-selection.md) when selecting the console operation: `run`
executes a flow, `dot` renders its graph, and `version` reports the engine version. These views
answer different questions about the same entry point, so neither is preferred or deprecated.

- code: `workflows/src/workhorse_workflows/coder/workflow.py::main`
- rule: use the composition-root concept for registry behavior and the command-selection concept for console operation; neither concept supersedes the other
- detail: [Coder entry point view selection](coder-entry-point-view-selection.md)
