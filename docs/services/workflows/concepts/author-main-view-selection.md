---
type: concept
slug: author-main-view-selection
title: Author main view selection
---
# Author main view selection

`workflows/src/workhorse_workflows/author/workflow.py::main` binds the Author registry's entry
point to the shared console-script factory. It does not select an alternative registry or command
implementation, so the documents grounded in that binding are complementary views rather than
competing implementations.

Start with [Author entry point responsibilities](author-entry-point-responsibilities.md) to locate
the shared binding. Use [Author workflow composition root](author-workflow-composition-root.md)
when the question concerns the registry's flows, blueprints, package root, or dry-run replies. Use
[workhorse-author command selection](workhorse-author-command-selection.md) when the question is
which console operation to invoke: `run` executes a flow, `dot` renders a graph, and `version`
reports the engine version. None of these views supersedes another because each answers a distinct
question about the same binding.

- rule: choose the entry-point responsibilities view to locate `main`, the composition-root view for registry behavior, and the command-selection view for console operation; no view is preferred or deprecated
