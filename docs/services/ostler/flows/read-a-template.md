---
type: flow
slug: read-a-template
title: Read a template
---
# Read a template

- start: the caller wants one template's kinds
- steps:
  - [ostler template find one](../planning.md#ostler-template-find-one)
- end: the caller reads the kind's name and default path
- verify: exit_status(code=0)
- verify: json_path(path="[0].name", equals="tpl")
- verify: json_path(path="[0].kinds[0].name", equals="note")
- verify: json_path(path="[0].kinds[0].default_path", equals="docs/note")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a template tpl with a note kind
