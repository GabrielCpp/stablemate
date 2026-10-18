---
type: concept
slug: loop-runner-command-selection
title: Loop-runner command selection
---
# Loop-runner command selection

The loop-runner console script binds its registry through
`workflows/src/workhorse_workflows/loop_runner/workflow.py::main`. That entry point delegates
subcommand selection to the Workhorse CLI: `run` executes the bound LoopRunner workflow, `dot`
renders its state graph, and `version` prints the installed Workhorse engine version.

Use `run` to execute the workflow. Use `dot` only when a Graphviz representation of the
registered state graph is needed, and `version` only to inspect the installed engine. The
commands are all current and none supersedes another because they provide different operations
on the same bound workflow.

- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::main` @a2ae9831bbc1
- rule: use `run` for execution, `dot` for graph rendering, and `version` for installed-engine identification; no command supersedes another
