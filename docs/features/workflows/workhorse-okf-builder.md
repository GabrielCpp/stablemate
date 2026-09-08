---
type: cli
slug: workhorse-okf-builder
title: workhorse-okf-builder
---
# workhorse-okf-builder

- binary: `workhorse-okf-builder`
- code: `workflows/src/workhorse_workflows/okf_builder/workflow.py::main`

Runs the backfill registry described by the [OKF-builder workflow composition root](concepts/okf-builder-workflow-composition-root.md). `run` starts its default builder or the registered web walkthrough; Workhorse owns parser and execution mechanics.

The [workhorse-okf-builder driver runbook](ops/workhorse-okf-builder.md) exercises this CLI in dry-run mode with checkpointed inputs.

## Commands


### run
- usage: `workhorse-okf-builder run [<flow>] [--params JSON] [--dry-run]`
- flags:
  - `--context-file PATH` selects the context manifest for this run.
  - `--params JSON` supplies checkpointed builder or walkthrough inputs.
  - `--params-file PATH` supplies workflow parameters from a JSON object.
  - `--cli NAME`, `--profile NAME`, and `--config PATH` select the agent harness and configuration.
  - `--runs-dir DIR` and `--run-id ID` select the run-artifact location and stable identity.
  - `--dry-run` runs registered deterministic stand-ins.
  - `--resume-run PATH`, `--resume-latest`, and `--no-cache` select resume or fresh-run behavior.
- args:
  - `<flow>` selects `walkthrough-web`; omitting it starts OkfBuilder.
- does:
  - starts the selected registered backfill flow
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/okf_builder/workflow.py::main`
- detail: [OKF-builder command selection](concepts/okf-builder-command-selection.md)

### dot
- usage: `workhorse-okf-builder dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does:
  - renders the registered builder and walkthrough state graphs
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/okf_builder/workflow.py::main`
- detail: [OKF-builder command selection](concepts/okf-builder-command-selection.md)

### version
- usage: `workhorse-okf-builder version`
- does:
  - prints the installed Workhorse engine version
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/okf_builder/workflow.py::main`
- detail: [OKF-builder command selection](concepts/okf-builder-command-selection.md)
