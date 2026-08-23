---
type: runbook
slug: claims-api-qa-stack
title: QA stack
---
# QA stack

- driver: web
- environment: [Local auth emulator](auth-emulator.md)
- surfaces: [Claims API](../http/claims-api.md)
- code: compose.yml
- entry-url: http://localhost:18085
- health-path: /healthz
- identity: `"status":"ok"` — a substring of the health *body*, exactly as served
- reuse: never
- boot-timeout: 240

The launch rebuilds. Unlike a bind-mounted interpreter, a seeded defect in Go only reaches the
running process through a compile, so `--build` is what makes a defect variant take effect at all.

The boot budget is larger than policy-desk's because coming up means three services, one of which
is a JVM: the auth emulator has to answer before the seed can create the three identities, and the
API refuses to be called until they exist.

`reuse: never` because a container already serving is a container built from the *previous*
trial's tree: adopting it would test the last defect variant and report the result against this one.

## Steps

### serve

- kind: service
- run: docker compose -f compose.yml up -d --build --force-recreate --wait
- health: curl -fsS http://localhost:18085/healthz
