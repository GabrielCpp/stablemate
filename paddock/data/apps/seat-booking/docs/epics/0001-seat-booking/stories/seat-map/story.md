---
type: story
id: SEAT-01KZYBWG0HRS6TVX8761VS6GYX
slug: seat-map
status: Not started
---
# Story: Render the seat map

## Dependencies

(none)

## Fixtures

- Fixture: (none)

<!-- The showing is arranged over the documented route — `DELETE /api/showing` puts every seat
back to `free` — so a scenario reaches its starting state through the product rather than
around it. There is nothing here for a fixture to set up that the API does not already
expose. -->

## Context

The showing has to be visible before anything can be taken. This story stands up the service
itself — the ledger, the seat vocabulary of three rows by four — and the two read surfaces over it:
the JSON seat map at [GET /api/seats](../../../../features/booking/http/seat-booking-api.md#get-seat-map)
and the server-rendered [seat map screen](../../../../features/booking/gui/screens/seat-map.md) the
API serves on `/`. It also lands `/healthz`, because everything that waits for the stack to come up
waits on that.

Nothing here mutates a seat. Every seat is free, and the point of the story is that the map says so
in both places from the same read.

## Acceptance Criteria

- Every seat in the showing appears in the JSON map, in row-then-number order, with its `id`, `row`,
  `number`, `state` and `version`, and a taken seat is listed with its state rather than dropped.
- The page renders one button per seat, named by the seat id alone, carrying the seat's state as
  `data-state`, with a seat that is not free rendered `disabled`.
- The page's status line states how many of the showing's seats are free, counting only `free` ones.
- `GET /healthz` answers `200` with `{"status": "ok"}` without reading the ledger.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

No prior implementation reference exists.

## Implementation Status

- **Status**: Not started
