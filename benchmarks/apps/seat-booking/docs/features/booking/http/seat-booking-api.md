---
type: server
slug: seat-booking-api
title: Seat booking API
---
# Seat booking API

- code: app/service.py::Handler
- openapi: none; the service is five hand-routed paths over `http.server` and publishes no schema.

The seat booking API is the whole of the product's machine surface: one showing, twelve seats, and
three transitions a seat can make. It answers JSON on `/api/…`, serves the
[seat map screen](../gui/screens/seat-map.md) itself on `/`, and answers `/healthz` for whatever is
waiting on it to come up. Every route is a thin translation of one function on the
[seat](../concepts/seat.md) transition module: the route parses, calls, and serialises, so a refusal
the domain decides is the same refusal on the wire.

The journey that stitches the three transitions together is
[hold and confirm a seat](../flows/hold-and-confirm.md).

State lives in the [seat ledger](../concepts/seat-ledger.md) and nowhere else — no request is served
out of process memory, which is what lets a confirmed booking be observed after a restart rather than
merely after a write. Concurrency is a per-seat integer `version`: every transition bumps it, and
confirming a hold has to quote the number the caller was given.

## Endpoints

### get-health

- does: answers `200` with `{"status": "ok"}` as soon as the process is serving, reading no ledger.
- verify: http_status(200, path="/healthz")
- verify: json_path("status", equals="ok")
- code: app/service.py::Handler.do_GET
- route: `GET /healthz`
- parent: [Seat booking API](#seat-booking-api)
- request:
  - method: `GET`
  - path: `/healthz`
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"status": "ok"}`

### get-seat-map

- does: returns every seat in the showing, in row-then-number order, whatever state it is in.
- verify: http_status(200, path="/api/seats")
- verify: count(subject="seats", equals=12)
- does: gives each seat its `id`, `row`, `number`, `state` and `version`, so a client can render the
  map and confirm against it without a second request.
- verify: json_path("seats[0].id", equals="A1")
- verify: json_path("seats[0].version", absent=false)
- does: lists a taken seat with its state rather than dropping it, so the map keeps its shape as
  seats are sold.
- verify: json_path("seats[0].state", matches="free|held|booked")
- code: app/booking.py::seat_map
- route: `GET /api/seats`
- parent: [Seat booking API](#seat-booking-api)
- refs: [seat](../concepts/seat.md)
- request:
  - method: `GET`
  - path: `/api/seats`
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"seats": [{"id": str, "row": str, "number": int, "state": str, "version": int}, …]}`

### post-seat-hold

- does: moves a free seat to `held`, bumps its version, and returns the hold id together with the
  version the caller must quote to confirm.
- verify: http_status(201, path="/api/seats/A1/hold")
- verify: json_path("hold.version", equals="1")
- raises: `409 Seat Unavailable` when the seat is already held or already booked; the ledger is left
  as it was.
- verify: http_status(409, title="Seat Unavailable", path="/api/seats/A1/hold")
- verify: unchanged(subject="seat A1", except_fields=[])
- raises: `404 No Such Seat` for an id outside the showing's seat map.
- verify: http_status(404, title="No Such Seat", path="/api/seats/Z9/hold")
- code: app/booking.py::hold
- route: `POST /api/seats/{seat}/hold`
- parent: [Seat booking API](#seat-booking-api)
- refs: [seat](../concepts/seat.md)
- request:
  - method: `POST`
  - path: `/api/seats/{seat}/hold`
  - path variables: `seat` — a seat id such as `A1`; rows `A`-`C`, numbers `1`-`4`.
  - body: none
- response:
  - status: `201`
  - media: `application/json`
  - body: `{"hold": {"id": str, "seat": str, "version": int}}`
  - errors: `409 Seat Unavailable`, `404 No Such Seat`

### delete-seat-hold

- does: returns a held seat to `free`, bumps its version, and answers `204` with no body.
- verify: http_status(204, path="/api/seats/A1/hold")
- does: touches the released seat and no other — every other seat keeps its state, its version and
  its booking.
- verify: unchanged(subject="seats", except_fields=["A1.state", "A1.version", "A1.hold"])
- verify: keys_unchanged(subject="seats")
- raises: `409 Seat Not Held` when the seat is free or already booked, so a release cannot undo a
  confirmed booking.
- verify: http_status(409, title="Seat Not Held", path="/api/seats/B1/hold")
- code: app/booking.py::release
- route: `DELETE /api/seats/{seat}/hold`
- parent: [Seat booking API](#seat-booking-api)
- refs: [seat](../concepts/seat.md)
- request:
  - method: `DELETE`
  - path: `/api/seats/{seat}/hold`
  - path variables: `seat` — a seat id such as `A1`.
  - body: none
- response:
  - status: `204`
  - media: none
  - body: empty
  - errors: `409 Seat Not Held`, `404 No Such Seat`

### post-seat-booking

- does: turns a held seat into a booking under the given name, bumps its version, and returns the
  booking id.
- verify: http_status(201, path="/api/seats/A1/booking")
- verify: json_path("booking.name", equals="Dana Okonkwo")
- concurrency: refuses a request quoting a version other than the seat's current one with
  `409 Stale Hold`, so a caller who lost the seat and came back with the number it was given does
  not overwrite the booking that replaced it.
- verify: conflict_on_stale(subject="seat A1", token="version")
- verify: http_status(409, title="Stale Hold", path="/api/seats/A1/booking")
- persistence: a confirmed booking is written through the ledger before the response is sent, and is
  still there after the service restarts.
- verify: persists(subject="seat A1 booking")
- raises: `400 Version Required` when the body carries no integer `version`.
- verify: http_status(400, title="Version Required", path="/api/seats/A1/booking")
- raises: `400 Name Required` when the body carries no non-blank `name`.
- verify: http_status(400, title="Name Required", path="/api/seats/A1/booking")
- raises: `409 Seat Not Held` when the seat was never held, so a booking cannot be conjured out of a
  free seat.
- verify: http_status(409, title="Seat Not Held", path="/api/seats/C4/booking")
- code: app/booking.py::confirm
- route: `POST /api/seats/{seat}/booking`
- parent: [Seat booking API](#seat-booking-api)
- refs: [seat](../concepts/seat.md)
- request:
  - method: `POST`
  - path: `/api/seats/{seat}/booking`
  - path variables: `seat` — a seat id such as `A1`.
  - body: `{"version": int, "name": str}`
- response:
  - status: `201`
  - media: `application/json`
  - body: `{"booking": {"id": str, "seat": str, "name": str}}`
  - errors: `400 Version Required`, `400 Name Required`, `409 Seat Not Held`, `409 Stale Hold`,
    `404 No Such Seat`
