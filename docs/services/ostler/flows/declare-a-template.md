---
type: flow
slug: declare-a-template
title: Declare a template
---
# Declare a template

- start: a repo wants a new kind of document
- steps:
  - [ostler template new](../planning.md#ostler-template-new)
- end: the caller sees the template created with one kind
- verify: exit_status(code=0)
- verify: stdout(matches="^created template 'tpl3' \\(1 kind\\(s\\)\\)$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with two declared templates
