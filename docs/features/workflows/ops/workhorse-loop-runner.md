---
type: runbook
slug: workhorse-loop-runner
title: workhorse-loop-runner driver
---
# workhorse-loop-runner driver

This CLI runbook installs the workspace package and exercises the deterministic loop-runner
driver without requiring an agent CLI or repository context. The exposed surface is the
[workhorse-loop-runner CLI](../workhorse-loop-runner.md), whose console-script entry point is
`workflow.py::main`.

- driver: cli
- cli: [workhorse-loop-runner](../workhorse-loop-runner.md)
- surfaces: [workhorse-loop-runner](../workhorse-loop-runner.md)
- code: `workflows/src/workhorse_workflows/loop_runner/workflow.py::main` @a2ae9831bbc1
- working-directory: .

## Steps

### provision-workspace

- kind: prepare
- run: `uv sync --all-packages`
- working-directory: .
- timeout: 120

### check-driver

- kind: service
- run: `uv run workhorse-loop-runner version`
- timeout: 30
- health: `uv run workhorse-loop-runner version` exits 0 and prints the installed Workhorse engine version

### run-driver

- kind: run
- run: `uv run workhorse-loop-runner run --dry-run`
- timeout: 120
- produces: the Workhorse run result for the dry-run plan
- verify: [workhorse-loop-runner run command](../workhorse-loop-runner.md#run)
