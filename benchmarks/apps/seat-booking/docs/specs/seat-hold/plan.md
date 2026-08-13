---
type: spec.plan
---

# Plan: Hold a Seat

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it: the tree carries the finished service, and what runs against it is QA.

## 1. Approach

The service is Python's `http.server` with no third-party runtime dependency and no build step, so
it comes up from a stock interpreter image. The domain transitions live apart from the HTTP layer:
routes parse, call one function, and serialise, so a failing scenario names the rule rather than the
route.

## 2. Files

- `app/booking.py` — `hold` and `release`, plus the `Refused`/`Conflict` vocabulary the routes translate.
- `app/service.py` — `POST` and `DELETE` on `/api/seats/{seat}/hold`, and the conflict-to-status mapping.

## 3. Acceptance Checklist

- [x] Holding a free seat answers 201, moves it to `held`, bumps its version, and returns `{"hold": {"id", "seat", "version"}}`.
- [x] Holding a held or booked seat answers `409 Seat Unavailable` and leaves the ledger byte-identical.
- [x] An id outside the showing answers `404 No Such Seat`.
- [x] Releasing a held seat answers 204 with no body, returns it to `free`, and bumps its version.
- [x] A release leaves every other seat's state, version and booking untouched, and adds or removes no seat.
- [x] Releasing a free or booked seat answers `409 Seat Not Held`.

## 4. QA

Every claim above is observable over HTTP or on the rendered page. There is no unit-test surface to
cite: a sandboxed scenario has the service and nothing else on the far side of a forwarded port.

The showing is twelve seats and nothing refills it, so a scenario that needs a free seat must put
the showing back first — `DELETE /api/showing`, documented on the seat-booking API. QA drives this
service repeatedly (a rehearsal, the scored execution, a re-run after a repair), and a scenario that
assumes the pool it found the first time fails the second for having no seat left rather than for
anything this story claims.
