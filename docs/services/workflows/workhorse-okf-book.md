---
type: cli
slug: workhorse-okf-book
title: workhorse-okf-book
---
# workhorse-okf-book

- binary: `workhorse-okf-book`
- code: `workflows/src/workhorse_workflows/okf_book/workflow.py::main` @471692cad878

Writes, repairs and runs one OKF book per surface of an app. It registers the write, exercise and reground flows beside the main `OkfBook` flow. Workhorse supplies the command parser; this package supplies the registry.

## Commands

### run
- usage: `workhorse-okf-book run [--params JSON] [--dry-run]`
- flags:
  - `--params JSON` supplies the `surfaces` list, each entry naming a `service`, its `kind` and its `entry` folder.
  - `--params-file PATH` supplies workflow parameters from a JSON object.
  - `--cli NAME`, `--profile NAME`, and `--config PATH` select the agent harness and configuration.
  - `--runs-dir DIR` and `--run-id ID` select the run-artifact location and stable identity.
  - `--dry-run` walks the graph with the agent turns and the stack stubbed.
  - `--resume-run PATH`, `--resume-latest`, and `--no-cache` select resume or fresh-run behavior.
- does: starts the main OKF book flow
- fixture: none, because the dry run walks the graph with every agent turn and the stack stubbed
- run: invoke(argv=["run", "--dry-run", "--params", "{\"surfaces\":[{\"service\":\"workflows\",\"kind\":\"cli\",\"entry\":\"workflows\"}]}"])
- verify: exit_status(code=0)
- verify: stdout(matches="dry-run ok")
- code: `workflows/src/workhorse_workflows/okf_book/workflow.py::main` @471692cad878

### dot
- usage: `workhorse-okf-book dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does: renders the registered OkfBook state graph
- fixture: none, because the command reads only the installed package
- run: invoke(argv=["dot"])
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/okf_book/workflow.py::main` @471692cad878

### version
- usage: `workhorse-okf-book version`
- does: prints the installed Workhorse engine version
- fixture: none, because the command reads only the installed package
- run: invoke(argv=["version"])
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/okf_book/workflow.py::main` @471692cad878
