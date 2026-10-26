---
type: flow
slug: catch-a-fixture-set-naming-a-missing-file
title: Catch a fixture set naming a missing file
---
# Catch a fixture set naming a missing file

- start: a caller renders a stack with a `--fixtures` set a service declares, but one of the
  set's files does not exist
- steps:
  - [ostler env render](../environments.md#ostler-env-render-fixture-missing)
- end: the caller is told by name, and by the service that needs it, which fixture file is
  missing, before docker ever runs
- verify: json_path(path="ok", equals=false)
- verify: json_path(path="error", matches="^env-render-fixture:demo fixture set `okf-book-probe-missing` names .*/docs/services/env-render-fixture/ops/absent\\.env, which does not exist$")
- fixture: [environments render and secrets](../fixtures/environments-render-and-secrets.md) —
  seeds env-render-fixture's demo service with a `okf-book-probe-missing` fixture set naming a
  file no step ever creates
