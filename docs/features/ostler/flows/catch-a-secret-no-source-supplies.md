---
type: flow
slug: catch-a-secret-no-source-supplies
title: Catch a secret no source supplies
---
# Catch a secret no source supplies

- start: a service's template references a `${NAME}` the stack root's secret source does not
  define, and no upstream job's `outputs:` supplies it either
- steps:
  - [ostler env check](../environments.md#ostler-env-check-required-name)
- end: the caller is told by name and by the service that needs it which secret is missing,
  before docker ever runs
- verify: json_path(path="ok", equals=false)
- verify: json_path(path="errors[0]", matches="^a `\\$\\{NAME\\}` the templates require is in no secret source: `OKF_BOOK_PROBE_SECRET` is required by env-secrets-fixture:worker$")
- fixture: [environments render and secrets](../fixtures/environments-render-and-secrets.md) —
  seeds env-secrets-fixture, whose worker service's template references
  `${OKF_BOOK_PROBE_SECRET}`, and no stack root declares a secrets: source to supply it
