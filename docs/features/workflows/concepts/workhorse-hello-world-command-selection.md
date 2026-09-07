---
type: concept
slug: workhorse-hello-world-command-selection
title: workhorse-hello-world-command-selection
---
# Hello-world command selection

The hello-world console script binds its registry through
`workflows/src/workhorse_workflows/hello_world/workflow.py::main`. That entry point delegates
subcommand selection to the Workhorse CLI: `run` executes the bound HelloWorld workflow, `dot`
renders that workflow's state graph, and `version` prints the installed Workhorse engine version.

Use `run` to execute the workflow; it is also the default when no recognized subcommand is given.
Use `dot` only when a Graphviz representation of the registered state graph is needed, and use
`version` only to inspect the installed engine. The commands are all current and none supersedes
another because they provide different operations on the same bound workflow.

- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::main`
- rule: use `run` for execution, `dot` for graph rendering, and `version` for installed-engine identification; no command supersedes another
