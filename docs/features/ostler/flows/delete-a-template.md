---
type: flow
slug: delete-a-template
title: Delete a template
---
# Delete a template

- start: a template is no longer wanted
- steps:
  - [ostler template delete](../planning.md#ostler-template-delete)
- end: the caller sees the template deleted
- verify: exit_status(code=0)
- verify: stdout(matches="^deleted template 'tpl2'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a template tpl2
