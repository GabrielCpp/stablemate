---
type: concept
title: CLI dispatch
---
# CLI dispatch

A workflow package ships no command line of its own. It declares a `Registry` of its flows, and
its console script hands that registry to workhorse. Workhorse then builds the one parser every
workflow shares, with the program name `workhorse-<workflow>`. Passing anything other than a
`Registry` to the console-script factory raises a type error at import time, so a mis-wired
package fails before any command runs.

The command table holds six commands: `run`, `dot`, `control`, `inbox`, `replay` and `version`.
The first token picks one. When the first token is `-h` or `--help`, the top-level help prints.
When the argument list is empty, or its first token names no command, workhorse puts `run` in
front of it. So `workhorse-loop-runner --cli codex` and `workhorse-loop-runner run --cli codex` are the same
command, and a bare `workhorse-loop-runner` starts the workflow's entry flow.

Each command owns its own arguments and its own handler. The [`run`](../workhorse.md#run)
command is described under [run launch](run-launch.md), and the operator commands under
[run control](run-control.md) and [operator inbox](operator-inbox.md).

- code: `workhorse/workhorse/cli/__init__.py::main` @408aa8a4f987
- code: `workhorse/workhorse/cli/__init__.py::console_script` @408aa8a4f987
- code: `workhorse/workhorse/cli/__init__.py::ConsoleEntry` @408aa8a4f987
- code: `workhorse/workhorse/cli/parser.py::build_parser` @6b7ae77922ce
- code: `workhorse/workhorse/cli/parser.py::Command` @6b7ae77922ce
- code: `workhorse/workhorse/cli/README.md` @f36f361b7649
- code: `workhorse/workhorse/__init__.py` @331cdb028c18
- code: `workhorse/workhorse/pyflow/registry.py::Registry` @a2d3d9fd50b3
- code: `workhorse/workhorse/pyflow/registry.py::registry_of` @a2d3d9fd50b3
