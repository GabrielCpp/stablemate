---
type: flow
slug: hold-and-confirm
title: Hold and confirm a seat
---
# Hold and confirm a seat

- verify: visible(locator="status", text="11 of 12 seats free")
- start: [Seat map](../gui/screens/seat-map.md)
- verify: visible(locator="region:Seat map")
- verify: visible(locator="status", text="12 of 12 seats free")
- steps:
  - Open the seat map and read which seats are free from
    [the free-seat summary](../gui/screens/seat-map.md#free-seat-summary).
  - Take a free seat off the market with
    [POST /api/seats/{seat}/hold](../http/seat-booking-api.md#post-seat-hold), keeping the version it
    returns.
  - Either spend the hold with
    [POST /api/seats/{seat}/booking](../http/seat-booking-api.md#post-seat-booking), quoting that
    version and a name, or give it back with
    [DELETE /api/seats/{seat}/hold](../http/seat-booking-api.md#delete-seat-hold).
  - Reload the seat map: the seat now reads `booked` and is no longer clickable, and the summary has
    dropped by one.
- end: [Seat map](../gui/screens/seat-map.md)
- verify: visible(locator="status", text="11 of 12 seats free")
- tests:

The journey the whole product exists for, and the one that makes the version token observable: the
seat is held under one version, and only the caller quoting it can turn the hold into a booking. A
second party who held the seat earlier, lost it, and returns with the number they were given is
refused rather than served — which is the difference between a compare-and-swap and an unconditional
write, and cannot be seen from a single happy path.
