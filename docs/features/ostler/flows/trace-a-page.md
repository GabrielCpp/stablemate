---
type: flow
slug: trace-a-page
title: Trace a page
---
# Trace a page

- start: the caller names a page of the book
- steps:
  - [ostler trace](../book-checks.md#ostler-trace)
- end: the caller reads every link out of the page and whether each resolves
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^  → docs/features/demo/cli\\.md  \\[ok\\]$")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds an entries page that links the cli page and the flow
