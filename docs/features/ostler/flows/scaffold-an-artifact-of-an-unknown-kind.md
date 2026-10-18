---
type: flow
slug: scaffold-an-artifact-of-an-unknown-kind
title: Scaffold an artifact of an unknown kind
---
# Scaffold an artifact of an unknown kind

- start: a caller names a kind that is not among those `ostler artifact list` reports
- steps:
  - [ostler artifact scaffold](../cli.md#ostler-artifact-scaffold-unknown-kind)
- end: the caller is rejected before any spec file is touched, rather than getting a skeleton for
  a kind that does not exist
- verify: exit_status(code=1)
- fixture: none, because an unknown kind name fails before the spec directory is read or written
