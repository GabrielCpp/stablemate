---
type: concept
slug: research-command-selection
title: Research command selection
---
# Research command selection

The Research composition root constructs one registry and exposes its entry point as the
`workhorse-research` console script. It does not rank the CLI subcommands: all three are
current views of that shared entry point.

Use `run` to execute the registered Research flow, `dot` to render its registered state graph,
and `version` to report the installed Workhorse engine version. Selecting one is determined by
the caller's task, not by a preference or deprecation relationship.

- code: `workflows/src/workhorse_workflows/research/workflow.py::main`
- rule: select `run` to execute the Research flow, `dot` to inspect its state graph, or `version` to report the installed engine version; none supersedes the others
