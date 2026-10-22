---
type: flow
slug: audit-screen-reachability
title: Audit screen reachability
---
# Audit screen reachability

- start: a surface whose screens are declared in the book
- steps:
  - [ostler reach](../book-checks.md#ostler-reach)
- end: the caller reads that no screen of the surface lacks a click path
- verify: exit_status(code=0)
- verify: json_path(path="surface", equals="groom")
- fixture: none, because the groom book is tracked in the repo and holds one screen
