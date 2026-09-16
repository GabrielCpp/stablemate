---
type: runbook
slug: web-app-stack
title: web-app (local)
---
# web-app (local)

Brings up web-app alone against the same [local](../../api-service/ops/local.md)
environment [api-service (local)](../../api-service/ops/api-service-stack.md) uses. web-app
serves static files only; it has no server-side dependency on api-service, but the page it
serves calls api-service's origin directly from the browser, so a Playwright journey
through this surface needs api-service running too — that dependency is declared on the
[browse-and-add-widget](../flows/browse-and-add-widget.md) flow, not here, because this
runbook's own job is only to bring web-app up.

- driver: web
- environment: [local](../../api-service/ops/local.md)
- cli:
- surfaces: [widget-list](../gui/screens/widget-list.md)
- code: `compose.yml` @69d0b0918e8a
- entry-url: http://localhost:18102
- health-path: /healthz
- identity:
- reuse: if-fresh
- fresh: health-path responds 200 within 5s of the last known-good check
- boot-timeout: 30s
- health-timeout: 2s
- stop: `docker compose stop web-app`
- working-directory: `.`
- secrets:

## Steps

### serve
- kind: service
- run: `docker compose up --build web-app`
- working-directory: `.`
- timeout: 30s
- env:
- health: http_status(200, path="/healthz")
- produces: web-app listening on :18102
- verify: http_status(200, path="/healthz")
- optional: false
- depends-on:
