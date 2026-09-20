---
type: story
id: WDGT-01M2ZA8TBRYTGZWGKVABCRMJS5
slug: widget-list
status: Not started
---
# Story: Show the widget directory

## Dependencies

(none)

## Fixtures

(none)

## Context

The directory is web-app's landing page: everything on hand, read straight from api-service
by the browser itself. [The widget-list screen](../../../../features/web-app/gui/screens/widget-list.md)
is that page, and [browse-and-add-widget](../../../../features/web-app/flows/browse-and-add-widget.md)
is the one journey that starts and ends on it, crossing to the new-widget form and back.

The read has three outcomes, not one: a populated table, an empty-directory notice, and an
alert when the read itself fails. A story that only asks for the table stops short of the
part that actually distinguishes "nothing on file" from "could not find out" — those two are
different claims about the same blank space, and only one of them is a directory a reader
should trust.

## Acceptance Criteria

- `GET /api/widgets` answers `200` with every widget currently held by the store, in creation
  order.
- The directory renders one row per widget, naming each row's `name` and `quantity`.
- An empty directory renders a notice saying so, and no table.
- A directory that cannot be read renders an alert rather than an empty table.
- The directory page offers a link to the new-widget form, reachable by keyboard.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `app/api-service/store.go::Store.List` is the one route to the in-memory ledger; a
  directory served from anything else answers correctly only in that process.
- `app/api-service/service.go::Server.handleList` is the handler `Server.Routes` registers
  for `GET /api/widgets`, and `app/api-service/service.go::writeJSON` is the response writer
  it shares with every other endpoint — the shape a directory read succeeds or fails in is
  not specific to this route.
- `app/web-app/static/app.js::loadWidgets` is the browser's own fetch against api-service's
  origin; `app/web-app/static/app.js::renderWidgetTable` is what turns the response into the
  table-or-notice split the acceptance criteria ask for.

## Implementation Status

- **Status**: Not started
