---
type: concept
slug: research-workflow-package-initializer
title: Research workflow package initializer
---
# Research workflow package initializer

This package initializer exposes no workflow API of its own. Importers reach the research
machine through its `workflow` module, which owns the installed entry point, state graph, and
node registration. The initializer only establishes the package containing those modules.
