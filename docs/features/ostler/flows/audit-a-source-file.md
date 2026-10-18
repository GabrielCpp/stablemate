---
type: flow
slug: audit-a-source-file
title: Audit a source file
---
# Audit a source file

- start: a source file whose symbols the book may or may not cite
- steps:
  - [ostler audit](../book-checks.md#ostler-audit)
- end: the caller receives review packets for the file and no semantic decision
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="prepared")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds a source file with two functions
- detail: [Auditing a book's claims against source](../concepts/auditing-a-books-claims-against-source.md)
