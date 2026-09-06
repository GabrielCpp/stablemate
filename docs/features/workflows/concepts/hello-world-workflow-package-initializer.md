---
type: concept
slug: hello-world-workflow-package-initializer
title: Hello-world workflow package initializer
---
# Hello-world workflow package initializer

The package exists only to group the hello-world composition root and its prompt. It exports no
workflow API of its own; the `workhorse-hello-world` console script reaches
[the composition root](hello-world-workflow-composition-root.md) directly.

- code: `workflows/src/workhorse_workflows/hello_world/__init__.py`
