---
type: flow
slug: audit-a-go-source-file
title: Audit a Go source file
---
# Audit a Go source file

- start: a Go source file whose symbols the book may or may not cite
- steps:
  - [ostler audit Go](../book-checks.md#ostler-audit-go)
- end: the caller receives review packets for the file and no semantic decision
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="prepared")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds a Go source file with one function
- detail: [Auditing a book's claims against source](../concepts/auditing-a-books-claims-against-source.md)
