---
type: flow
slug: audit-a-typescript-source-file
title: Audit a TypeScript source file
---
# Audit a TypeScript source file

- start: a TypeScript source file whose symbols the book may or may not cite
- steps:
  - [ostler audit TypeScript](../book-checks.md#ostler-audit-typescript)
- end: the caller receives review packets for the file and no semantic decision
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="prepared")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds a TypeScript source file with one function
- detail: [Auditing a book's claims against source](../concepts/auditing-a-books-claims-against-source.md)
