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
- verify: http_status(200, path="/api/widgets")
- detail: the claim above is about the directory read this journey *ends* on, not about the
  create in the middle of it — that 201 is [post-widgets](../http/api-service.md#post-widgets)'s
  own claim, and restating it here would file one observation against two obligations and, worse,
  assert 201 against the response the last step actually produced. The stronger claim this
  journey wants — that the created widget is present in the listing, by id — is not expressible
  yet: it names a value from the request body, and `steps:` has no bullet for the data a step
  carries, so the compiler cannot ground it.
- fixture: [api-service (local)](../ops/api-service-stack.md) running against
  [local](../ops/local.md)
- tests:
