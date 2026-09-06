---
type: runbook
slug: workhorse-coder
title: workhorse-coder driver
---
# workhorse-coder driver

This CLI runbook installs the workspace package and exercises the coder driver in dry-run mode.
The selected flow and story or epic inputs are supplied through checkpointed `--params`; the
exposed surface is the [workhorse-coder CLI](../workhorse-coder.md).

- driver: cli
- cli: [workhorse-coder](../workhorse-coder.md)
- surfaces: [workhorse-coder](../workhorse-coder.md)
- code: `workflows/src/workhorse_workflows/coder/workflow.py::main`
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
- run: `uv run workhorse-coder version`
- timeout: 30
- health: `uv run workhorse-coder version` exits 0 and prints the installed Workhorse engine version
- provenance: derived

### run-driver

- kind: run
- run: `uv run workhorse-coder run --dry-run`
- timeout: 120
- produces: the Workhorse run result for the selected coder flow
- verify: [workhorse-coder run command](../workhorse-coder.md#run)
- provenance: derived
