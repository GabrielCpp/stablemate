---
type: cli
slug: workhorse-loop-runner
title: workhorse-loop-runner
---
# workhorse-loop-runner

- binary: `workhorse-loop-runner`
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::main` @a2ae9831bbc1
- detail: [loop-runner workflow](concepts/loop-runner-workflow.md)

Hands a plan to one agent turn and lets the agent's own tool-call loop carry it to completion. It needs no repository and no manifest, and under `--dry-run` it needs no agent CLI, so it is the command to run before trusting any other workflow. Workhorse supplies the command parser; this package supplies the registry and its only flow.

The [workhorse-loop-runner driver runbook](ops/workhorse-loop-runner.md) exercises this CLI in dry-run mode.

## Commands

### run
- usage: `workhorse-loop-runner run [--params JSON] [--dry-run]`
- flags:
  - `--context-file PATH` selects the context manifest for this run.
  - `--params JSON` supplies checkpointed workflow parameters; `plan` is the text handed to the agent and defaults to empty.
  - `--params-file PATH` supplies workflow parameters from a JSON object.
  - `--cli NAME`, `--profile NAME`, and `--config PATH` select the agent harness and configuration.
  - `--runs-dir DIR` and `--run-id ID` select the run-artifact location and stable identity.
  - `--dry-run` answers the agent turn with a deterministic summary instead of calling an agent CLI.
  - `--resume-run PATH`, `--resume-latest`, and `--no-cache` select resume or fresh-run behavior.
- does:
  - sends `plan` to the agent in a single turn and returns the agent's summary
- run: invoke(argv=["run", "--dry-run"])
- verify: exit_status(code=0)
- fixture: none, because the command reads only the installed package
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::main` @a2ae9831bbc1
- detail: [Loop-runner command selection](concepts/loop-runner-command-selection.md)

### dot
- usage: `workhorse-loop-runner dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does:
  - renders the registered LoopRunner state graph
- run: invoke(argv=["dot"])
- verify: exit_status(code=0)
- fixture: none, because the command reads only the installed package
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::main` @a2ae9831bbc1
- detail: [Loop-runner command selection](concepts/loop-runner-command-selection.md)

### version
- usage: `workhorse-loop-runner version`
- does:
  - prints the installed Workhorse engine version
- run: invoke(argv=["version"])
- verify: exit_status(code=0)
- fixture: none, because the command reads only the installed package
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::main` @a2ae9831bbc1
- detail: [Loop-runner command selection](concepts/loop-runner-command-selection.md)
