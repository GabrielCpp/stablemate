---
type: concept
slug: package-root-entry-point-imports
title: Package root entry point imports
---
# Package root entry point imports

`workhorse/workhorse/__init__.py::__all__` exposes `console_script` and `main` from
`workhorse.cli` without adding workflow discovery or execution during import. The two
imports are the same callables at different boundaries, not separate implementations.

Use `workhorse.console_script` when a workflow distribution binds its
`[project.scripts]` command. Use `workhorse.main` only for the rare caller that invokes
an already-bound workflow directly. Refer to `workhorse.cli.console_script` or
`workhorse.cli.main` when describing or maintaining CLI composition and dispatch.

- rule: bind a workflow distribution command through `workhorse.console_script`; use the package-root `main` only for direct invocation, and use the `workhorse.cli` imports only in CLI implementation context
