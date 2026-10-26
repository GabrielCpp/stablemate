---
type: cli
slug: workhorse-new
title: workhorse-new
---
# workhorse-new

- binary: `workhorse-new`
- code: `workflows/src/workhorse_workflows/new/scaffold.py::main` @e93136a05eae

Writes a standalone workflow distribution. Its single agent turn loops until a shell check exits 0. The command is not a workflow itself.

## Commands

### new
- usage: `workhorse-new NAME --check COMMAND [--into DIR]`
- args: `NAME` is the workflow name, written in lowercase letters, digits and single dashes, and the new command becomes `workhorse-NAME`.
- flags:
  - `--check COMMAND` is the shell command that decides when the work is done.
  - `--into DIR` is the directory to create `NAME` in, defaulting to the current directory.
- does: writes the distribution into `DIR/NAME` from the bundled template
- fixture: none, because the command creates everything its check observes
- run: invoke(argv=["fix-tests", "--check", "true", "--into", "."])
- verify: created(subject="fix-tests/pyproject.toml")
- code: `workflows/src/workhorse_workflows/new/scaffold.py::main` @e93136a05eae

The bundled template carries its own `CheckLoop` workflow, copied verbatim into every new
distribution under its package folder, with `__WORKFLOW_NAME__` and `__CHECK__` placeholders that
`scaffold.py::main` fills with the requested name and check command. `CheckLoop` hands the task to
one agent turn, runs the check command with a shell in the repo, and loops back with the check's
output until it exits 0 or `max_rounds` is spent.

- code: `workflows/src/workhorse_workflows/new/template/package/workflow.py::CheckLoop` @45e0698c357d
- code: `workflows/src/workhorse_workflows/new/template/package/workflow.py::run_check` @45e0698c357d
