---
type: runbook
slug: workhorse-hello-world
title: workhorse-hello-world driver
---
# workhorse-hello-world driver

This CLI runbook installs the workspace package and exercises the deterministic hello-world
driver without requiring an agent CLI or repository context. The exposed surface is the
[workhorse-hello-world CLI](../workhorse-hello-world.md), whose console-script entry point is
`workflow.py::main`.

- driver: cli
- cli: [workhorse-hello-world](../workhorse-hello-world.md)
- surfaces: [workhorse-hello-world](../workhorse-hello-world.md)
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::main`
- working-directory: .

## Steps

### provision-workspace

- kind: prepare
- run: `uv sync --all-packages`
- working-directory: .
- timeout: 120
- provenance: derived

### check-driver

- kind: service
- run: `uv run workhorse-hello-world version`
- timeout: 30
- health: `uv run workhorse-hello-world version` exits 0 and prints the installed Workhorse engine version
- provenance: derived

### run-driver

- kind: run
- run: `uv run workhorse-hello-world run --dry-run`
- timeout: 120
- produces: the Workhorse run result for the deterministic greeting
- verify: [workhorse-hello-world run command](../workhorse-hello-world.md#run)
- provenance: derived
