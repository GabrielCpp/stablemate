---
type: flow
slug: create-a-templated-document
title: Create a templated document
---
# Create a templated document

- start: a repo declares a note kind
- steps:
  - [ostler new instance](../planning.md#ostler-new-instance)
- end: the caller reads the created document's name
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", equals="created note 'n1'")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a declared note kind
