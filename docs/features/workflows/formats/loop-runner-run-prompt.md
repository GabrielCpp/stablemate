---
type: format
slug: loop-runner-run-prompt
title: Loop-runner run prompt
---
# Loop-runner run prompt

The [loop-runner workflow](../concepts/loop-runner-workflow.md) renders this template for its
only agent turn. The template is the plan text itself, with no wrapper around it.

- file: `workflows/src/workhorse_workflows/loop_runner/prompts/run.md`
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::LoopRunner.start` @a2ae9831bbc1

## Fields

### plan

- type: `str`
- default: empty
- semantics: the plan the agent carries out, taken from the `plan` workflow parameter
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::LoopRunner.start` @a2ae9831bbc1
