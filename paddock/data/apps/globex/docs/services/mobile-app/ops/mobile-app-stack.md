---
type: runbook
slug: mobile-app-stack
title: mobile-app (local)
---
# mobile-app (local)

Brings up mobile-app's Metro bundler alone against the same
[local](../../api-service/ops/local.md) environment
[api-service (local)](../../api-service/ops/api-service-stack.md) uses. mobile-app is a client
app; it has no server-side dependency on api-service, but the screens it renders call
api-service's origin directly from the device's own network, so a Maestro journey through this
surface needs api-service running too — that dependency is declared on the
[browse-and-add-widget](../flows/browse-and-add-widget.md) flow, not here, because this
runbook's own job is only to bring mobile-app up.

- driver: mobile
- environment: [local](../../api-service/ops/local.md)
- cli:
- surfaces: [widget-list](../gui/screens/widget-list.md), [new-widget](../gui/screens/new-widget.md)
- code: `app/mobile-app/.maestro/browse-and-add-widget.flow.yaml` @73d6429162ff
- entry-url:
- health-path:
- identity:
- bundle-id: com.globex.mobile
- launch-screen: [widget-list](../gui/screens/widget-list.md)
- reuse:
- fresh:
- boot-timeout:
- health-timeout:
- stop:
- working-directory: `app/mobile-app`
- secrets:

## Steps

### serve
- kind: service
- run: `npm start`
- working-directory: `app/mobile-app`
- timeout: 30s
- env:
- health: `curl -fsS http://localhost:8081/status`
- produces: Metro bundler serving mobile-app
- verify:
- optional: false
- depends-on:
