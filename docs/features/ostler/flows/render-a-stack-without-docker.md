---
type: flow
slug: render-a-stack-without-docker
title: Render a stack without docker
---
# Render a stack without docker

- start: a caller wants the compose file a book's services would produce, without starting docker
- steps:
  - [ostler env render](../environments.md#ostler-env-render)
- end: the caller has a compose.yml and manifest written into a named copy's directory, and
  docker was never invoked
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="services[0]", equals="env-render-fixture:demo")
- fixture: [environments render and secrets](../fixtures/environments-render-and-secrets.md) —
  seeds env-render-fixture, one service whose template references no secret
