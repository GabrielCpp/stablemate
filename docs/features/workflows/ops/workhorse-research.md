---
type: runbook
slug: workhorse-research
title: workhorse-research driver
---
# workhorse-research driver

This CLI runbook installs the workspace package and exercises the research driver in dry-run
mode. A real research run receives its program and repository selection through checkpointed
`--params`; the exposed surface is the [workhorse-research CLI](../workhorse-research.md).

- driver: cli
- cli: [workhorse-research](../workhorse-research.md)
- surfaces: [workhorse-research](../workhorse-research.md)
- code: `workflows/src/workhorse_workflows/research/workflow.py::main`
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
- run: `uv run workhorse-research version`
- timeout: 30
- health: `uv run workhorse-research version` exits 0 and prints the installed Workhorse engine version
- provenance: derived

### run-driver

- kind: run
- run: `uv run workhorse-research run --dry-run`
- timeout: 120
- produces: the Workhorse run result for the configured research program
- verify: [workhorse-research run command](../workhorse-research.md#run)
- provenance: derived
