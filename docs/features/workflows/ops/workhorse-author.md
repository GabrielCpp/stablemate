---
type: runbook
slug: workhorse-author
title: workhorse-author driver
---
# workhorse-author driver

This CLI runbook installs the workspace package and exercises the author driver in dry-run mode.
The selected flow and roadmap inputs are supplied through checkpointed `--params`; the exposed
surface is the [workhorse-author CLI](../workhorse-author.md).

- driver: cli
- cli: [workhorse-author](../workhorse-author.md)
- surfaces: [workhorse-author](../workhorse-author.md)
- code: `workflows/src/workhorse_workflows/author/workflow.py::main`
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
- run: `uv run workhorse-author version`
- timeout: 30
- health: `uv run workhorse-author version` exits 0 and prints the installed Workhorse engine version
- provenance: derived

### run-driver

- kind: run
- run: `uv run workhorse-author run --dry-run`
- timeout: 120
- produces: the Workhorse run result for the selected authoring flow
- verify: [workhorse-author run command](../workhorse-author.md#run)
- provenance: derived
