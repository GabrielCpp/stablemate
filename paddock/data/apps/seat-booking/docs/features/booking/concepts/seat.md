---
type: concept
slug: seat
title: Seat
---
# Seat

- code: app/booking.py
- extends:

A seat is one place at tonight's showing, addressed by a row letter (`A`-`C`) and a number (`1`-`4`).
Twelve of them make the whole product's domain. A seat is always in exactly one of three states —
`free`, `held`, `booked` — and carries an integer `version` that every transition increments; that
number is the compare-and-swap token [POST /api/seats/{seat}/booking](../http/seat-booking-api.md#post-seat-booking)
requires, and the reason a lost hold cannot be spent twice.

The three transitions below are the whole state machine. They live apart from the HTTP layer so that
a scenario that fails names the rule rather than the route: `service.py` translates each refusal into
a status code and decides nothing. Each also lives in a module of its own, cited from the method that
documents it — this node owns the projection and the shared refusal vocabulary in `app/booking.py`,
and nothing else — so a defect seeded in one transition is grounded at that transition and localizes
to it. The durable side — where the states are written and how — is
[the seat ledger](seat-ledger.md); the rendered side is
[the seat map screen](../gui/screens/seat-map.md).

## Methods

### hold

- sig: `hold(store: Store, seat: str) -> dict`
- abstract: takes a free seat off the market for whoever is deciding, and hands back the version to
  confirm against.
- verify: json_path("hold.version", equals="1")
- raises: `Seat Unavailable` when the seat is held or booked, leaving the ledger untouched.
- verify: unchanged(subject="seat A1", except_fields=[])
- raises: `No Such Seat` for an id that is not in the showing.
- verify: http_status(404, title="No Such Seat")
- code: app/hold.py::hold
- does: moves the seat from `free` to `held` and increments its version.
- concurrency: seat-record — the version it hands back is the seat's own, so a hold taken while
  another caller is deciding cannot be spent against a stale token.
- parent: [Seat](#seat)

### release

- sig: `release(store: Store, seat: str) -> None`
- abstract: gives a held seat back to the showing.
- verify: http_status(204)
- verify: unchanged(subject="seats", except_fields=["A1.state", "A1.version", "A1.hold"])
- raises: `Seat Not Held` when the seat is free or booked, so releasing cannot undo a booking.
- verify: http_status(409, title="Seat Not Held")
- code: app/hold.py::release
- does: moves the seat from `held` to `free`, increments its version, and clears the hold.
- does: writes exactly the released seat; every other seat keeps its state, version and booking.
- concurrency: seat-record — the release increments the version like any other transition, so the
  hold it gave back cannot be confirmed afterwards.
- parent: [Seat](#seat)

### confirm

- sig: `confirm(store: Store, seat: str, *, version: int, name: str) -> dict`
- abstract: spends a hold on a booking in somebody's name.
- verify: json_path("booking.name", equals="Dana Okonkwo")
- raises: `Seat Not Held` when the seat was never held.
- verify: http_status(409, title="Seat Not Held")
- code: app/confirm.py::confirm
- does: moves the seat from `held` to `booked`, increments its version, and records the booking name.
- concurrency: seat-record — refuses a caller quoting any version but the seat's current one, which is what makes
  a hold spendable exactly once.
- verify: conflict_on_stale(subject="seat A1", token="version")
- parent: [Seat](#seat)
