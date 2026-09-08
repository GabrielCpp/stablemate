---
type: cli
slug: workhorse-research
title: workhorse-research
---
# workhorse-research

- binary: `workhorse-research`
- code: `workflows/src/workhorse_workflows/research/workflow.py::main`
- detail: [research workflow schemas](concepts/research-schemas.md)

Runs the research gate loop registered by the [research workflow composition root](concepts/research-workflow-composition-root.md). Workhorse provides the shared command parser; this package provides the default Research flow.

The [workhorse-research driver runbook](ops/workhorse-research.md) exercises this CLI in dry-run mode with checkpointed inputs.

## Commands


### run
- usage: `workhorse-research run [--params JSON] [--dry-run]`
- flags:
  - `--context-file PATH` selects the context manifest for this run.
  - `--params JSON` supplies checkpointed Research inputs, including `program`, repository selection, and reauthorization.
  - `--params-file PATH` supplies workflow parameters from a JSON object.
  - `--cli NAME`, `--profile NAME`, and `--config PATH` select the agent harness and configuration.
  - `--runs-dir DIR` and `--run-id ID` select the run-artifact location and stable identity.
  - `--dry-run` runs the registered deterministic stand-ins.
  - `--resume-run PATH`, `--resume-latest`, and `--no-cache` select resume or fresh-run behavior.
- does:
  - starts the registered Research flow
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/research/workflow.py::main`
- detail: [Research command selection](concepts/research-command-selection.md)

### dot
- usage: `workhorse-research dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does:
  - renders the registered Research state graph
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/research/workflow.py::main`
- detail: [Research command selection](concepts/research-command-selection.md)

### version
- usage: `workhorse-research version`
- does:
  - prints the installed Workhorse engine version
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/research/workflow.py::main`
- detail: [Research command selection](concepts/research-command-selection.md)
