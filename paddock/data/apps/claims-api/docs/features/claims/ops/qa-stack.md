---
type: runbook
slug: claims-api-qa-stack
title: QA stack
---
# QA stack

- driver: http
- environment: [Local auth emulator](auth-emulator.md)
- surfaces: [Claims API](../http/claims-api.md)
- code: compose.yml@8061abd30646
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

`app`'s own `/healthz` proves the API process is listening, not that the identities the plan is
about to sign in as are actually usable — `service_completed_successfully` orders the containers
correctly, but the emulator's REST surface has its own brief warm-up after its liveness probe
starts answering, and a scenario that signs in during that window sees `EMAIL_NOT_FOUND` for an
account `seed` already reported creating. The `confirm-seed` step below signs in as the seed's own
first identity and is retried the same way `serve`'s gate is, so a plan lane never starts against a
stack whose seed has not actually landed.

## Steps

### serve

- kind: service
- run: docker compose -f compose.yml up -d --build --force-recreate --wait
- health: curl -fsS http://localhost:18085/healthz

### confirm-seed

- kind: health
- run: curl -fsS -X POST "http://localhost:18086/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=fake-api-key" -H "Content-Type: application/json" -d "{\"email\":\"holder-a@example.com\",\"password\":\"claims-bench-a\",\"returnSecureToken\":true}"
