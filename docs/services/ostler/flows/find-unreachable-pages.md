---
type: flow
slug: find-unreachable-pages
title: Find unreachable pages
---
# Find unreachable pages

- start: every page of a book links from its entries page
- steps:
  - [ostler gc](../book-checks.md#ostler-gc)
- end: the caller is told every page is reachable
- verify: exit_status(code=0)
- verify: stdout(matches="^every page is reachable$")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds a book whose entries page links every other page
