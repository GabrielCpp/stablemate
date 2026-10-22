---
type: flow
slug: trace-a-token-no-node-names
title: Trace a token no node names
---
# Trace a token no node names

- start: the caller names a token that matches no node
- steps:
  - [ostler trace on an unknown token](../book-checks.md#ostler-trace-unknown)
- end: the caller is told no node was found, and the exit status is an error
- verify: exit_status(code=1)
- verify: stdout(matches="^no node found for 'nothing-here'$")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds a book no token `nothing-here` names
