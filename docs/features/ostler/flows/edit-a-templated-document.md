---
type: flow
slug: edit-a-templated-document
title: Edit a templated document
---
# Edit a templated document

- start: a note needs a title
- steps:
  - [ostler set instance](../planning.md#ostler-set-instance)
- end: the caller sees the note updated
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", equals="updated note 'n2'")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a note n2
