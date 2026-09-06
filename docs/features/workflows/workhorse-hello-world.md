---
type: cli
slug: workhorse-hello-world
title: workhorse-hello-world
---
# workhorse-hello-world

- binary: `workhorse-hello-world`
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::main`

Runs the single-machine greeting example registered by the [hello-world workflow composition root](concepts/hello-world-workflow-composition-root.md). Its command parser is supplied by Workhorse; this package supplies the registry and its default flow.

## Commands


### run
- usage: `workhorse-hello-world run [--params JSON] [--dry-run]`
- flags:
  - `--context-file PATH` selects the context manifest for this run.
  - `--params JSON` supplies checkpointed workflow parameters; `name` defaults to `world`.
  - `--params-file PATH` supplies workflow parameters from a JSON object.
  - `--cli NAME`, `--profile NAME`, and `--config PATH` select the agent harness and configuration.
  - `--runs-dir DIR` and `--run-id ID` select the run-artifact location and stable identity.
  - `--dry-run` runs the registered deterministic stand-ins without an agent CLI.
  - `--resume-run PATH`, `--resume-latest`, and `--no-cache` select resume or fresh-run behavior.
- does:
  - starts the registered HelloWorld flow
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::main`

### dot
- usage: `workhorse-hello-world dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does:
  - renders the registered HelloWorld state graph
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::main`

### version
- usage: `workhorse-hello-world version`
- does:
  - prints the installed Workhorse engine version
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::main`
