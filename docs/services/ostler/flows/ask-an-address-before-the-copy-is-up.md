---
type: flow
slug: ask-an-address-before-the-copy-is-up
title: Ask an address before the copy is up
---
# Ask an address before the copy is up

- start: a caller wants the URL a named copy publishes a service at, and nothing has rendered or
  brought that copy up yet
- steps:
  - [ostler env address](../environments.md#ostler-env-address-not-up)
- end: the caller is told the copy is not up, rather than being given a stale or guessed address
- verify: json_path(path="ok", equals=false)
- verify: json_path(path="error", matches="^okf-book-env-address-never-up publishes no `demo` \\(it publishes none, since it is not up\\)$")
- fixture: none, because nothing is seeded
