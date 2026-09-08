---
type: concept
slug: console-script-import-selection
title: Console script import selection
---
# Console script import selection

`workhorse.console_script` is the import for a workflow distribution's
`[project.scripts]` target. The package root exports that callable as the library's
public wiring surface, while `workhorse.cli.console_script` is the same callable at
the module that owns CLI composition and dispatch. They are not alternate entry-point
implementations: choose the package-root import when binding a workflow command, and
the CLI-module reference only when describing or maintaining the CLI implementation.

- code: `workhorse/workhorse/__init__.py::__all__`
- code: `workhorse/workhorse/cli/__init__.py::console_script`
- rule: import `workhorse.console_script` to bind a workflow distribution's command; use `workhorse.cli.console_script` only for CLI implementation context because the package root re-exports that same callable
- detail: [Console script documentation selection](console-script-documentation-selection.md)
- detail: [Package root entry point imports](package-root-entry-point-imports.md)
- detail: [Console script concept scope](console-script-concept-scope.md)
