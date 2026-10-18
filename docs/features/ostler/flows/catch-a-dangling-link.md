---
type: flow
slug: catch-a-dangling-link
title: Catch a dangling link
---
# Catch a dangling link

- start: an entries page links to a page that does not exist
- steps:
  - [ostler doctor on a broken book](../book-checks.md#ostler-doctor-dangling-link)
- end: the caller is told which page holds the link, and the exit status stops a gate
- verify: exit_status(code=1)
- verify: json_path(path="findings[0].code", equals="dangling-link")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds `book-scratch-broken/`, whose entries page links to a missing page
