---
type: flow
slug: search-the-book
title: Search the book
---
# Search the book

- start: the caller has words from a question about the product
- steps:
  - [ostler search](../book-checks.md#ostler-search)
- end: the caller reads the matching pages with their paths
- verify: exit_status(code=0)
- verify: json_path(path="[0].path", equals="docs/services/demo/flows/say-hello.md")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds a flow titled "Say hello"
