---
type: concept
slug: loop-runner-workflow
title: Loop-runner workflow
---
# Loop-runner workflow

The `workhorse-loop-runner` console script imports `main`, which binds a registry to the
single-state `LoopRunner` machine. The machine hands its `plan` parameter to one agent turn and
finishes with that turn's [outcome](../formats/loop-runner-outcome.md). The agent's own tool-call
loop does the work inside the turn, so the flow adds no loop of its own. The turn renders the
[run prompt](../formats/loop-runner-run-prompt.md).

The registry carries no blueprint nodes. Under `--dry-run` the outcome declares its own
deterministic summary, so the whole machine runs without an agent CLI.

- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::workflow` @a2ae9831bbc1
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::main` @a2ae9831bbc1
- detail: [Loop-runner command selection](loop-runner-command-selection.md)
- detail: [Loop-runner package](loop-runner-package.md)

## Methods

### start

Runs the only agent turn and completes the workflow with its typed reply.

- sig: `LoopRunner.start(self) -> Done`
- does: renders the run prompt with the `plan` parameter
- does: validates the agent reply as an Outcome before using it
- does: logs the outcome summary
- returns: a Done result carrying the validated Outcome
- verify: json_path(path="$.summary", equals="Dry run: plan not actually carried out.")
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::LoopRunner.start` @a2ae9831bbc1
