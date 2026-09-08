---
type: concept
slug: workhorse-author-command-selection
title: workhorse-author command selection
---
# workhorse-author command selection

`workflow.py::main` binds the Author registry entry point to the shared console-script factory.
That composition root supplies no command-specific implementation, deprecation, or preference:
`run`, `dot`, and `version` are all current operations of the same `workhorse-author` surface.

Use `run` to execute the default Author flow or a selected registered flow, `dot` to render the
registered flow graphs, and `version` to report the installed Workhorse engine version. These
commands are complementary rather than replacements, so no command supersedes another.

- code: `workflows/src/workhorse_workflows/author/workflow.py::main`
- rule: select the command for the required operation: execution with `run`, graph rendering with `dot`, or engine identification with `version`; no command is preferred or deprecated
- detail: [author entry point responsibilities](author-entry-point-responsibilities.md)
- detail: [author main view selection](author-main-view-selection.md)
