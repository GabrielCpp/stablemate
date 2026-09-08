---
type: concept
slug: main-import-selection
title: Main import selection
---
# Main import selection

`workhorse.main` and `workhorse.cli.main` name the same dispatcher; selecting an import path
does not select different command behavior. The package root re-exports the dispatcher as the
library's public direct-call API, while the CLI module is the implementation location that builds
the parser, supplies the workflow registry, and dispatches a selected command.

Workflow distributions normally use `console_script`, which binds a workflow registry and calls
the dispatcher itself. A caller that must invoke an already-bound workflow directly imports
`workhorse.main`; CLI implementation and maintenance documentation uses `workhorse.cli.main` to
locate the dispatcher. Neither path is deprecated, and the CLI path remains the legitimate
location for the console-script closure.

- code: `workhorse/workhorse/cli/__init__.py::main`
- rule: import `workhorse.main` for the public direct-call API; use `workhorse.cli.main` only to locate the CLI implementation
- prefers: [package root main export](package-exports.md#main)
- detail: [Main dispatcher concept scope](main-dispatcher-concept-scope.md)
