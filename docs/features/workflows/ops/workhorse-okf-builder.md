---
type: runbook
slug: workhorse-okf-builder
title: workhorse-okf-builder driver
---
# workhorse-okf-builder driver

This CLI runbook installs the workspace package and exercises the OKF-builder driver in dry-run
mode. A real build receives its service and source paths through checkpointed `--params`; the
exposed surface is the [workhorse-okf-builder CLI](../workhorse-okf-builder.md).

- driver: cli
- cli: [workhorse-okf-builder](../workhorse-okf-builder.md)
- surfaces: [workhorse-okf-builder](../workhorse-okf-builder.md)
- code: `workflows/src/workhorse_workflows/okf_builder/workflow.py::main`
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
- run: `uv run workhorse-okf-builder version`
- timeout: 30
- health: `uv run workhorse-okf-builder version` exits 0 and prints the installed Workhorse engine version
- provenance: derived

### run-driver

- kind: run
- run: `uv run workhorse-okf-builder run --dry-run`
- timeout: 120
- produces: the Workhorse run result for the OKF-builder flow
- verify: [workhorse-okf-builder run command](../workhorse-okf-builder.md#run)
- provenance: derived
