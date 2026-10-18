---
type: flow
slug: list-templated-documents
title: List templated documents
---
# List templated documents

- start: the caller wants every note
- steps:
  - [ostler find instances](../planning.md#ostler-find-instances)
- end: the caller reads each note's name and path
- verify: exit_status(code=0)
- verify: json_path(path="[0].type", equals="note")
- verify: json_path(path="[0].path", matches="^docs/note/n[0-9]/note\\.md$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a declared note kind with two notes
