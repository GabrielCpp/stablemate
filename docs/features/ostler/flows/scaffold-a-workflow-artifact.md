---
type: flow
slug: scaffold-a-workflow-artifact
title: Scaffold a workflow artifact
---
# Scaffold a workflow artifact

- start: no backlog-items.json artifact exists in the spec dir yet
- verify: absent(subject="artifact-flow-spec/backlog-items.json")
- steps:
  - [ostler artifact scaffold](../cli.md#ostler-artifact-scaffold)
- end: an empty backlog-items.json skeleton is written to the spec dir
- verify: contents(subject="artifact-flow-spec/backlog-items.json", matches="(?s)^\\[\\]\\n$")
- fixture: none, because starting from an empty spec dir needs no seeded state
