---
type: flow
slug: check-a-book-is-sound
title: Check a book is sound
---
# Check a book is sound

- start: a book whose citations carry no digest stamp and whose links all resolve
- steps:
  - [ostler doctor](../book-checks.md#ostler-doctor)
- end: the caller reads zero errors, so a gate on the exit status lets the book through
- verify: exit_status(code=0)
- verify: json_path(path="errors", equals=0)
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds a sound `demo` book that reports warnings and no error
- detail: [Book health: coverage, reach and census](../concepts/book-health-coverage-reach-and-census.md)
