---
type: runbook
slug: policy-desk-qa-stack
title: QA stack
---
# QA stack

- driver: web
- surfaces: [Policy desk API](../http/policy-desk-api.md)
- code: app/api/service.go
- entry-url: http://localhost:18084
- health-path: /healthz
- identity: `"status": "ok"` — a substring of the health *body*, not a host:port
- reuse: never
- boot-timeout: 120

The launch rebuilds. Unlike a bind-mounted interpreter, a seeded defect in Go or TSX only
reaches the running process through a compile, so `--build` is what makes a defect variant
take effect at all — without it a trial would score against the previous trial's binary.

`reuse: never` for the same reason: adopting whatever already answers `/healthz` with the
identity marker would adopt the *previous* trial's container, and the seeded defect would not
be in the service under test at all. That is a clean miss no report could explain.

Deliberately **no** `down -v` in the launch. A bring-up is not once per trial — `ensure_stack`
runs at the head of every plan lane, so a story taking more than one lap gets its stack
re-launched while it is being observed. Destroying the volume in that window empties the
ledger under a durability the product actually has. The reset lives one layer up, in the
harness (`benchmarks/replay.py`), which drops the volume once before the run starts.

## Steps

### serve

- kind: service
- run: docker compose -f compose.yml up -d --build --force-recreate --wait
- health: curl -fsS http://localhost:18084/healthz

### register

- kind: health
- run: curl -fsS http://localhost:18084/api/policies
