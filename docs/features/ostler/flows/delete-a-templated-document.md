---
type: flow
slug: delete-a-templated-document
title: Delete a templated document
---
# Delete a templated document

- start: a note is no longer wanted
- steps:
  - [ostler remove instance](../planning.md#ostler-remove-instance)
- end: the caller sees the note deleted
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", equals="deleted note 'n3'")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a note n3
