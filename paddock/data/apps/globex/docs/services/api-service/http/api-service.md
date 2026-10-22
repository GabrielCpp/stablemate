---
type: server
slug: api-service
title: Widget directory API
---
# Widget directory API

A small JSON API over an in-process [widget](../concepts/widget.md) list. It answers only
`api-service`'s own routes — CORS is enabled so `web-app`'s browser client can call it
directly from a different origin, but nothing here calls out to `web-app`; the two services
never talk to each other server-to-server.

- code: `app/api-service/service.go::Server` @0344dec13901
- code: `app/api-service/main.go` @e155b187eb7d
- openapi:
- detail:
- launch:
- entry-url: http://localhost:18101
- health-path: /healthz
- working-directory:
- identity:
- stop:
- boot-timeout:
- walkthrough:

## Endpoints

### get-health
- method: GET
- path: /healthz
- channel:
- message:
- does:
  - report the process is up, with no dependency on the widget store
- emits:
- consumes:
- status: 200
- verify: http_status(200, path="/healthz")
- errors:
- auth: none
- fixture:
- capture:
- code: `app/api-service/service.go::Server.handleHealth` @0344dec13901
- openapi:
- detail:
- tests: `app/api-service/service_test.go::TestHandleHealth`

### get-widgets
- method: GET
- path: /api/widgets
- channel:
- message:
- does:
  - return every widget currently held by the store, in creation order
- emits:
- consumes:
- status: 200
- verify: http_status(200, path="/api/widgets")
- errors:
- auth: none
- fixture:
- capture:
- code: `app/api-service/service.go::Server.handleList` @0344dec13901
- openapi:
- detail:
- tests: `app/api-service/service_test.go::TestHandleList`

### post-widgets
- method: POST
- path: /api/widgets
- channel:
- message:
- does: all
  - create a widget from `name` and `quantity` and assign it the next generated id
  - return the created widget in the response body
- emits:
- consumes: `{name: string, quantity: integer}`
- status: 201
- verify: http_status(201, path="/api/widgets")
- arrange: body(field="name", value="Widget A")
- arrange: body(field="quantity", value=3)
- errors: 422 with a `{errors: {field: message}}` body when a blank `name` or a negative
  `quantity` is refused rather than coerced
- verify: http_status(422, path="/api/widgets")
- arrange: body(field="name", value="")
- auth: none
- fixture:
- capture:
- code: `app/api-service/service.go::Server.handleCreate` @0344dec13901
- openapi:
- detail:
- tests: `app/api-service/service_test.go::TestHandleCreate`
