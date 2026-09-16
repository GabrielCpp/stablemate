---
type: runbook
slug: api-service-stack
title: api-service (local)
---
# api-service (local)

Brings up api-service alone against the [local](local.md) environment. This runbook and
[web-app (local)](../../web-app/ops/web-app-stack.md) share that one environment node —
each names only its own surface, so the two can run independently or together under the
same compose project.

- driver: http
- environment: [local](local.md)
- cli:
- surfaces: [api-service](../http/api-service.md)
- code: `compose.yml` @69d0b0918e8a
- entry-url: http://localhost:18101
- health-path: /healthz
- identity:
- reuse: if-fresh
- fresh: health-path responds 200 within 5s of the last known-good check
- boot-timeout: 30s
- health-timeout: 2s
- stop: `docker compose stop api-service`
- working-directory: `.`
- secrets:

## Steps

### serve
- kind: service
- run: `docker compose up --build api-service`
- working-directory: `.`
- timeout: 30s
- env:
- health: http_status(200, path="/healthz")
- produces: api-service listening on :18101
- verify: http_status(200, path="/healthz")
- optional: false
- depends-on:
