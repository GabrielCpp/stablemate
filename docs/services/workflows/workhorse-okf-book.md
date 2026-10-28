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
  - `--params JSON` supplies the `surfaces` list, each entry naming a `service`, its `kind` (`cli`, `http`, `web`, `mobile` or `grpc`) and its `entry` folder. A `grpc` surface also names a `contract` folder of `.proto` files, and an `http` surface may. A `repo` field names the workspace member that holds the product: it is required under a workspace and refused outside one. See [okf-book workspace surface](concepts/okf-book-workspace-surface.md).
  - `--params-file PATH` supplies workflow parameters from a JSON object.
  - `--cli NAME`, `--profile NAME`, and `--config PATH` select the agent harness and configuration.
  - `--runs-dir DIR` and `--run-id ID` select the run-artifact location and stable identity.
  - `--dry-run` walks the graph with the agent turns and the stack stubbed.
  - `--resume-run PATH`, `--resume-latest`, and `--no-cache` select resume or fresh-run behavior.
- does:
  - starts the main OKF book flow
- run: invoke(argv=["run", "--dry-run", "--params", "{\"surfaces\":[{\"service\":\"workflows\",\"kind\":\"cli\",\"entry\":\"workflows\"}]}"])
- verify: exit_status(code=0)
- verify: stdout(matches="dry-run ok")
- fixture: none, because the dry run walks the graph with every agent turn and the stack stubbed
- code: `workflows/src/workhorse_workflows/okf_book/workflow.py::main` @471692cad878

### dot
- usage: `workhorse-okf-book dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does:
  - renders the registered OkfBook state graph
- run: invoke(argv=["dot"])
- verify: exit_status(code=0)
- fixture: none, because the command reads only the installed package
- code: `workflows/src/workhorse_workflows/okf_book/workflow.py::main` @471692cad878

### version
- usage: `workhorse-okf-book version`
- does:
  - prints the installed Workhorse engine version
- run: invoke(argv=["version"])
- verify: exit_status(code=0)
- fixture: none, because the command reads only the installed package
- code: `workflows/src/workhorse_workflows/okf_book/workflow.py::main` @471692cad878
