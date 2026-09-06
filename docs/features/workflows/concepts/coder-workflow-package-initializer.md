---
type: concept
slug: coder-workflow-package-initializer
title: Coder workflow package initializer
---
# Coder workflow package initializer

The package groups the Coder workflow's composition root, default epic-and-story machine, seven
registered sub-flow machines, and shared helpers. The composition root is the only console-script
entry point; every flow remains callable by its registered name, and prompt paths are relative to
this package directory.

- code: `workflows/src/workhorse_workflows/coder/__init__.py`
