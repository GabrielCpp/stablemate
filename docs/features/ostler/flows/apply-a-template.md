---
type: flow
slug: apply-a-template
title: Apply a template
---
# Apply a template

- start: a template is declared but its folders are missing
- steps:
  - [ostler template apply](../planning.md#ostler-template-apply)
- end: the caller reads how many folders were created
- verify: exit_status(code=0)
- verify: stdout(matches="^applied template 'tpl' \\(1 dir\\(s\\) scaffolded\\)$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a template tpl whose note folder is missing
