---
type: flow
slug: search-the-book
title: Search the book
---
# Search the book

- start: the caller remembers part of a page's title
- steps:
  - [ostler search](../book-checks.md#ostler-search)
- end: the caller reads the matching pages with their paths
- verify: exit_status(code=0)
- verify: json_path(path="[1].path", equals="docs/services/demo/flows/say-hello.md")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds a flow titled "Say hello"
