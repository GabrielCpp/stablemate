---
type: concept
slug: research-workflow-package-initializer
title: Research workflow package initializer
---
# Research workflow package initializer

The `workhorse_workflows.research` package establishes the composition root by providing a
Python state machine implementation of the gate-ladder experiment loop. The package contains the
`workflow` module, which owns the installed entry point, state graph, and node registration. The
package's docstring documents the port from the original YAML-based implementation in the
base library.

- code: `workflows/src/workhorse_workflows/research/__init__.py`
- detail: [research workflow composition root](research-workflow-composition-root.md)
- detail: [research nodes package initializer](research-nodes-package-initializer.md)
