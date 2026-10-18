---
type: flow
slug: diagnose-and-wire-a-repository
title: Diagnose and wire a repository
---
# Diagnose and wire a repository

An operator checks a repository's farrier setup, lists the workflows installed on the machine and wires the pre-commit drift check into the repository's hook manager.

- start: a repository holds an `agents.yml`
- steps:
  - [diagnose the repository](../farrier-invocations.md#diagnose-the-repository)
  - [list installed workflows](../farrier-invocations.md#list-installed-workflows)
  - [wire the hook manager](../farrier-invocations.md#wire-the-hook-manager)
- end: the hook manager file carries farrier's fenced entry (commands: [workflows](../farrier-commands-workflows.md#workflows), [doctor](../farrier-commands-workflows.md#doctor), [hooks](../farrier-commands-workflows.md#hooks))
- verify: contents(subject="c211/.husky/pre-commit", text="make farrier-run-hook")
- fixture: bare-agents-yml dir=c209
- fixture: pipx-two-workflows dir=c210
- fixture: husky-repo dir=c211
- detail: [hook manager wiring](../concepts/hook-manager-wiring.md)
