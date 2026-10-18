---
type: flow
slug: catch-a-malformed-stack-file
title: Catch a malformed stack file
---
# Catch a malformed stack file

- start: a book's ops/stack.yml does not parse to a mapping with a services key
- steps:
  - [ostler env check](../cli.md#ostler-env-check)
- end: the caller is told by name and path which stack file is broken, rather than the problem
  being skipped silently
- verify: json_path(path="ok", equals=false)
- verify: json_path(path="errors[0]", matches="^docs/features/env-check-fixture/ops/stack\\.yml: is not a mapping with a `services:` key$")
- fixture: env-check-fixture creates docs/features/env-check-fixture/ops/stack.yml, a stack file
  whose top level is a YAML list rather than a mapping
