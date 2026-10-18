---
type: flow
slug: initialize-and-render-repository
title: Initialize and render repository
---
# Initialize and render repository

The render also writes the launcher outputs that farrier owns, from the resolved library.

- start: a repository directory exists without an `agents.yml` configuration
- verify: absent(subject="c200/agents.yml")
- steps:
  - [write the starter config](../farrier-invocations.md#write-starter-config)
  - [render the selected adapters](../farrier-invocations.md#render-selected-adapters)
- end: the repository contains the starter `agents.yml` and selected agent adapters (commands: [init](../farrier-commands-init.md#init), [install](../farrier-commands-install.md#install))
- verify: created(subject="c200/agents.yml")
- verify: created(subject="c201/.claude/skills/acme-demo/SKILL.md")
- fixture: empty-dir dir=c200
- fixture: demo-skill-repo dir=c201
- detail: [agents.yml installer config](../formats/agents-yml-config.md)
- detail: [renderer](../concepts/renderer.md)
