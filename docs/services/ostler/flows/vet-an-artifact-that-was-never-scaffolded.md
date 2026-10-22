---
type: flow
slug: vet-an-artifact-that-was-never-scaffolded
title: Vet an artifact that was never scaffolded
---
# Vet an artifact that was never scaffolded

- start: no backlog-items.json artifact exists in the spec dir yet
- verify: absent(subject="artifact-vet-missing-spec/backlog-items.json")
- steps:
  - [ostler artifact vet](../cli.md#ostler-artifact-vet)
- end: the caller is told to scaffold the artifact first, rather than being told it is clean
- verify: exit_status(code=1)
- fixture: none, because the claim is that a never-scaffolded spec dir is rejected
