---
type: concept
slug: loop-runner-package
title: Loop-runner package
---
# Loop-runner package

The `workhorse_workflows.loop_runner` package exports nothing of its own. It exists to hold the
[workflow](loop-runner-workflow.md) and its prompt, and its docstring states the contract: one
plan goes to one agent turn, and the target CLI's tool-call loop carries it to completion.

- code: `workflows/src/workhorse_workflows/loop_runner/__init__.py` @efc9ca3acc34
