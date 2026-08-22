---
type: story
id: SEAT-01KZYBWGDCHS2F6WEYJN41C6E5
slug: seat-hold
status: Not started
---
# Story: Hold a seat

## Dependencies

(none)

## Fixtures

- Fixture: (none)

<!-- The showing is arranged over the documented route — `DELETE /api/showing` puts every seat
back to `free` — so a scenario reaches its starting state through the product rather than
around it. There is nothing here for a fixture to set up that the API does not already
expose. -->

## Context

A seat has to be reservable before it can be sold. This story adds the first two transitions —
[hold](../../../../features/booking/concepts/seat.md#hold) and
[release](../../../../features/booking/concepts/seat.md#release) — and the endpoints over them.

The narrow write is the part worth stating: releasing one seat must touch that seat only. A release
implemented by rebuilding the map from a fresh showing looks correct from the released seat and is
wrong from every other one, which is why the criterion is about the neighbours rather than about the
seat that changed.

## Acceptance Criteria

- Holding a free seat answers `201`, moves it to `held`, bumps its version, and returns the hold id
  together with the version to confirm against.
- Holding a seat that is held or booked answers `409 Seat Unavailable` and leaves the ledger as it
  was; an id outside the showing answers `404 No Such Seat`.
- Releasing a held seat answers `204`, returns it to `free`, and bumps its version.
- A release writes exactly the released seat: every other seat keeps its state, its version and its
  booking, and no seat appears or disappears from the map.
- Releasing a seat that is free or booked answers `409 Seat Not Held`.

## Implementation Status

- **Status**: Not started
