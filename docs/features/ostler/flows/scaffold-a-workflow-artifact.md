---
type: flow
slug: scaffold-a-workflow-artifact
title: Scaffold a workflow artifact
---
# Scaffold a workflow artifact

- start: no backlog-items.json artifact exists in the spec dir yet
- verify: absent(subject="cli-book-scaffold-spec/backlog-items.json")
- steps:
  - [ostler artifact scaffold](../cli.md#ostler-artifact-scaffold)
- end: an empty backlog-items.json skeleton is written to the spec dir
- verify: contents(subject="cli-book-scaffold-spec/backlog-items.json", matches="(?s)^\\[\\]\\n$")
- fixture: [cli scenario arrangement](../fixtures/cli-scenario-arrangement.md) — seeds an empty
  cli-book-scaffold-spec/ under the repo root, so --spec resolves there instead of under the specs root
