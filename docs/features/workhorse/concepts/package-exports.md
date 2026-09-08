---
type: concept
slug: package-exports
title: workhorse package exports
---
# workhorse package exports

The import package is a library boundary, not a command. Its public root namespace contains
only the two callables used by a workflow distribution to bind and invoke its own console
script; importing `workhorse` does not discover a workflow or execute one. Submodules remain
available through their own package paths but are not part of this root export contract.

- code: `workhorse/workhorse/__init__.py::__all__`
- detail: [Package root entry point imports](package-root-entry-point-imports.md)
- detail: [CLI composition and workflow binding](cli-composition.md)

## Methods

### console_script
- sig: `workhorse.console_script(workflow: Registry) -> ConsoleEntry`
- code: `workhorse/workhorse/cli/__init__.py::console_script`
- detail: [CLI composition and workflow binding](cli-composition.md#console_script)
- detail: [Console script import selection](console-script-import-selection.md)

This root export is the same callable implemented by `workhorse.cli.console_script`. A workflow
module passes its own `Registry` and receives the callable it names in `[project.scripts]`; the
package root does not add name resolution or run the workflow while it is imported.

### main
- sig: `workhorse.main(argv: list[str] | None, *, workflow: str, registry: Registry) -> None`
- code: `workhorse/workhorse/cli/__init__.py::main`
- detail: [CLI composition and workflow binding](cli-composition.md#main)
- detail: [Main import selection](main-import-selection.md)

This root export is the same command dispatcher implemented by `workhorse.cli.main`. It is
available for callers that want to invoke the already-bound workflow entry directly, while the
normal console-script path calls the callable returned by `console_script`.
