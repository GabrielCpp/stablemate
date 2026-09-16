---
type: flow
slug: add-widget-via-api
title: Add a widget via the API
---
# Add a widget via the API

api-service's own journey, driven by a `python` HTTP client against its endpoints directly
— nobody's browser is involved. This is not "the back half" of
[browse-and-add-widget](../../web-app/flows/browse-and-add-widget.md): it is a separate
actor (an API caller) exercising a separate contract (the JSON API), independently
verifiable with api-service running alone and web-app not running at all.

- start: [api-service](../http/api-service.md)
- steps:
  - [post-widgets](../http/api-service.md#post-widgets)
  - [get-widgets](../http/api-service.md#get-widgets)
- end: [api-service](../http/api-service.md)
- verify: http_status(201, path="/api/widgets")
- detail: the created widget is asserted present in the subsequent `GET /api/widgets`
  listing by id.
- fixture: [api-service (local)](../ops/api-service-stack.md) running against
  [local](../ops/local.md)
- tests:
