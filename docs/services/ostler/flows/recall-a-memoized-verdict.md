---
type: flow
slug: recall-a-memoized-verdict
title: Recall a memoized verdict
---
# Recall a memoized verdict

- start: a packet's claim has no verdict memoized yet, under a contract digest and a store of
  its own
- steps:
  - [verdict-memo-recall](../standalone-programs.md#verdict-memo-recall)
- end: the same claim, keyed by its own digest and the candidate pool beside it, recalls the
  verdict a prior review stored for it, without a fresh review ever running
- verify: exit_status(code=0)
- fixture: [memo scratch dir](../fixtures/memo-scratch-dir.md)
- detail: [Auditing a book's claims against source](../concepts/auditing-a-books-claims-against-source.md)
