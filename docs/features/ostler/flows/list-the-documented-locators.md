---
type: flow
slug: list-the-documented-locators
title: List the documented locators
---
# List the documented locators

- start: a surface whose controls are documented in the book
- steps:
  - [ostler locators](../book-checks.md#ostler-locators)
- end: the caller reads that no control collides and none is unlocatable
- verify: exit_status(code=0)
- verify: json_path(path="counts.unlocatable", equals=0)
- fixture: none, because the groom book is tracked in the repo and its controls all locate
