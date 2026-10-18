---
type: format
slug: loop-runner-outcome
title: Loop-runner outcome
---
# Loop-runner outcome

The [loop-runner workflow](../concepts/loop-runner-workflow.md) accepts this typed reply only
after the agent's JSON validates, then returns it as the workflow result.

- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::Outcome` @a2ae9831bbc1

## Fields

### summary

- type: `str`
- required: true because the agent reply must provide a summary
- semantics: what the agent reports once the plan is carried out
- verify: json_path(path="$.summary", equals="Dry run: plan not actually carried out.")
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::Outcome` @a2ae9831bbc1
