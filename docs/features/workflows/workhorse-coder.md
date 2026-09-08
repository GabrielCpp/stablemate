---
type: cli
slug: workhorse-coder
title: workhorse-coder
---
# workhorse-coder

- binary: `workhorse-coder`
- code: `workflows/src/workhorse_workflows/coder/workflow.py::main`
- detail: [coder shared library](concepts/coder-shared-library.md)
- detail: [operational runbooks index](concepts/ops-runbooks.md)

Runs the Coder registry described by the [Coder workflow composition root](concepts/coder-workflow-composition-root.md). `run` selects its default Coder flow or one of the registered coder flows.

The [workhorse-coder driver runbook](ops/workhorse-coder.md) exercises this CLI in dry-run mode. The [coder unit tests runbook](ops/coder-unit-tests.md) drives the full composition root with real workflow nodes.

## Commands


### run
- usage: `workhorse-coder run [<flow>] [--params JSON] [--dry-run]`
- flags:
  - `--context-file PATH` selects the context manifest for this run.
  - `--params JSON` supplies checkpointed inputs to the selected coder flow.
  - `--params-file PATH` supplies workflow parameters from a JSON object.
  - `--cli NAME`, `--profile NAME`, and `--config PATH` select the agent harness and configuration.
  - `--runs-dir DIR` and `--run-id ID` select the run-artifact location and stable identity.
  - `--dry-run` runs registered deterministic stand-ins.
  - `--resume-run PATH`, `--resume-latest`, and `--no-cache` select resume or fresh-run behavior.
- args:
  - `<flow>` selects `genesis`, `dev`, `review`, `docs`, `qa`, `fix`, or `fix_ci`; omitting it starts Coder.
- does:
  - starts the selected registered coder flow
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/workflow.py::main`
- detail: [Coder command selection](concepts/coder-command-selection.md)

### dot
- usage: `workhorse-coder dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does:
  - renders the registered Coder and selectable-flow state graphs
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/workflow.py::main`
- detail: [Coder command selection](concepts/coder-command-selection.md)

### version
- usage: `workhorse-coder version`
- does:
  - prints the installed Workhorse engine version
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/coder/workflow.py::main`
- detail: [Coder command selection](concepts/coder-command-selection.md)
