---
type: story
id: WDGT-01M2ZA8TVDMQVERJ9DNQ0KCKTB
slug: add-widget
status: Not started
---
# Story: Write a widget into the directory

## Dependencies

- Blocked by: widget-list

## Fixtures

(none)

## Context

Nothing in the directory reads until something writes, so this story is the write path for
[the widget concept](../../../../features/api-service/concepts/widget.md) end to end: the
store, the create endpoint, and the two clients that post to it.

There are two separate ways in. [The new-widget screen](../../../../features/web-app/gui/screens/new-widget.md)
is the browser's own cross-origin POST, form-driven and refused per field. [add-widget-via-api](../../../../features/api-service/flows/add-widget-via-api.md)
is a second, independent actor — an API caller against [api-service](../../../../features/api-service/http/api-service.md)
directly, with no browser and no form involved — and both have to land on the same store
rule: a widget is accepted only with a non-empty `name` and a `quantity` of zero or more.

## Acceptance Criteria

- A complete `POST /api/widgets` answers `201`, creates the widget from `name` and `quantity`,
  and assigns it the next generated id.
- A blank `name` or a negative `quantity` answers `422` with a `{errors: {field: message}}`
  body, refused rather than coerced.
- The new-widget form renders each field's error message beside the field it names, from that
  same `errors` body, rather than as one blob.
- A successful submission returns the browser to the directory, which now shows the created
  widget.
- The created widget is present in a subsequent `GET /api/widgets`, independent of whether it
  was created by the form or by a direct API call.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `app/api-service/store.go::Store.Create` and `app/api-service/store.go::ErrInvalidWidget`
  are where the accept/refuse rule actually lives — a blank name kept as blank, a negative
  quantity refused rather than clamped to zero.
- `app/api-service/service.go::Server.handleCreate` is the handler `Server.Routes` registers
  for `POST /api/widgets`, and `app/api-service/service.go::writeErrors` is what turns an
  `*ErrInvalidWidget` into the `{errors: {field: message}}` body both clients parse.
- `app/web-app/static/new.js::submitNewWidget` is the browser's own POST and the code that
  reads that body back into the per-field error spans on refusal, or redirects to the
  directory on success.

## Implementation Status

- **Status**: Not started
