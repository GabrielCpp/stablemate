---
type: concept
slug: coder-command-selection
title: Coder command selection
---
# Coder command selection

The Coder composition root constructs one registry, registers the selectable workflow flows, and
exposes its entry point as the `workhorse-coder` console script. It does not rank the CLI
subcommands: all three are current views of that shared entry point.

Use `run` to execute a selected Coder flow, `dot` to render the registered flow graphs, and
`version` to report the installed Workhorse engine version. Selecting one is determined by the
caller’s task, not by a preference or deprecation relationship.

- code: `workflows/src/workhorse_workflows/coder/workflow.py::main`
- rule: select `run` to execute a flow, `dot` to inspect flow graphs, or `version` to report the installed engine version; none supersedes the others
- detail: [Coder entry point view selection](coder-entry-point-view-selection.md)
