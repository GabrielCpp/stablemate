---
type: flow
slug: list-the-templates
title: List the templates
---
# List the templates

- start: the caller wants the templates a repo declares
- steps:
  - [ostler template find](../planning.md#ostler-template-find)
- end: the caller reads each template and its kind count
- verify: exit_status(code=0)
- verify: json_path(path="[0].name", equals="tpl")
- verify: json_path(path="[0].kinds", equals=1)
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with two declared templates
