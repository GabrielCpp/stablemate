---
type: flow
slug: initialize-and-render-repository
title: Initialize and render repository
---
# Initialize and render repository

- start: a repository directory exists without an `agents.yml` configuration
- verify: absent(subject="<repo>/agents.yml")
- steps:
-  - [init](../farrier.md#init)
-  - [install](../farrier.md#install)
- end: the repository contains the starter `agents.yml` and selected agent adapters
- verify: created(subject="<repo>/agents.yml")
- verify: created(subject="selected agent adapter files")
- end: the repository contains Farrier-owned launcher outputs rendered from the resolved library
- verify: persists(subject="Farrier-owned repository launcher outputs")
- detail: [agents.yml installer config](../agents-yml-config.md)
- detail: [renderer](../concepts/renderer.md)
