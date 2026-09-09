---
type: concept
slug: workhorse-cli-boilerplate-commands
title: Workhorse CLI boilerplate commands
---
# Workhorse CLI boilerplate commands

Every workhorse CLI distribution (`workhorse-author`, `workhorse-coder`, `workhorse-hello-world`, `workhorse-okf-builder`, `workhorse-research`) exposes the same three commands: `run`, `dot`, and `version`. The first is flow-specific; the latter two are boilerplate registry introspection tools provided by the Workhorse CLI harness (implemented in the `workhorse` package).

## dot

Renders the registered Workflow's composition graph in [Graphviz DOT format](https://graphviz.org/doc/info/lang.html), showing all registered flows and their dependencies. Useful for visualizing the state machine structure and understanding how flows connect. Output may be piped to `dot -Tpng` to generate a PNG, or written to a file for inspection.

## version

Prints the installed Workhorse engine version — the version of the `workhorse` distribution and runtime that the CLI distribution depends on. Used in CI and ops to confirm the installed engine matches expected deployed versions.

