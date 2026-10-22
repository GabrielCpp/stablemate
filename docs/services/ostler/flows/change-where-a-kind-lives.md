---
type: flow
slug: change-where-a-kind-lives
title: Change where a kind lives
---
# Change where a kind lives

- start: a kind's documents move to another folder
- steps:
  - [ostler template edit](../planning.md#ostler-template-edit)
- end: the caller sees the template updated
- verify: exit_status(code=0)
- verify: stdout(matches="^updated template 'tpl2'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a template tpl2 with a memo kind
