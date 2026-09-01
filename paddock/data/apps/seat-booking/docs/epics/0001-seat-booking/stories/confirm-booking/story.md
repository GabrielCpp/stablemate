---
type: story
id: SEAT-01KZYBWGTTBHHWQ9FYDRVYYT74
slug: confirm-booking
status: Not started
---
# Story: Confirm a held seat

## Dependencies

- Blocked by: seat-hold

## Fixtures

- Fixture: (none)

<!-- The showing is arranged over the documented route — `DELETE /api/showing` puts every seat
back to `free` — so a scenario reaches its starting state through the product rather than
around it. There is nothing here for a fixture to set up that the API does not already
expose. -->

## Context

The transition the product exists for, and the only one with a concurrency contract:
[confirm](../../../../features/booking/concepts/seat.md#confirm) spends a hold on a booking, and it
must be spendable exactly once. The per-seat `version` the hold handed back is the compare-and-swap
token; a caller quoting any other number is refused rather than served.

The booking also has to be durable. It is written through the
[seat ledger](../../../../features/booking/concepts/seat-ledger.md) before the response announcing it
is sent, so it survives a restart — a booking that lives only in the memory of the process that
answered is not a booking.

## Acceptance Criteria

- Confirming a held seat with the current version and a name answers `201`, moves the seat to
  `booked`, bumps its version, and returns the booking id and name.
- A request quoting any version other than the seat's current one answers `409 Stale Hold` and does
  not overwrite the booking that replaced it.
- A body with no integer `version` answers `400 Version Required`; a body with no non-blank `name`
  answers `400 Name Required`.
- Confirming a seat that was never held answers `409 Seat Not Held`.
- A confirmed booking is still in the map, with the same name, after the service is restarted.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `app/hold.py::hold` is what mints the version the caller quotes back here; the token is the
  seat's own `version` field, not a separate hold sequence.
- `app/hold.py::release` is the other spender of a hold, so both transitions must agree on what
  clears one — a confirm that leaves the hold in place makes a later release look valid.
- `app/store.py::Store` remains the single reader and writer, which is what makes the survives-a-restart
  criterion a property of this code path rather than of the deployment.
- `app/booking.py::seat_record` resolves the seat and `app/booking.py::Conflict` carries the
  refusals `app/service.py::Handler` turns into `409`, so the stale-hold case needs no new plumbing.

## Implementation Status

- **Status**: Not started
