---
type: spec.plan
---

# Plan: Confirm a Held Seat

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it: the tree carries the finished service, and what runs against it is QA.

## 1. Approach

The service is Python's `http.server` with no third-party runtime dependency and no build step, so
it comes up from a stock interpreter image. The domain transitions live apart from the HTTP layer:
routes parse, call one function, and serialise, so a failing scenario names the rule rather than the
route.

## 2. Files

- `app/booking.py` — `confirm`, the version comparison, and the `Stale Hold` refusal.
- `app/service.py` — `POST /api/seats/{seat}/booking`, body validation, and the 400/409 mapping.

## 3. Acceptance Checklist

- [x] Confirming a held seat with its current version and a name answers 201, moves it to `booked`, bumps its version, and returns `{"booking": {"id", "seat", "name"}}`.
- [x] A request quoting any other version answers `409 Stale Hold` and does not overwrite the booking that replaced it.
- [x] A body with no integer `version` answers `400 Version Required`.
- [x] A body with no non-blank `name` answers `400 Name Required`.
- [x] Confirming a seat that was never held answers `409 Seat Not Held`.
- [x] A confirmed seat is still `booked`, at the version the confirmation returned, under the same
  name, after the service is restarted — stated against the seat map because that is where the
  documented API shows it. The map lists a `booking` on a booked seat for exactly this reason: a
  durability criterion naming the booking would otherwise be asking QA to prove a claim through a
  field the product never publishes.

## 4. QA

Every claim above is observable over HTTP or on the rendered page. There is no unit-test surface to
cite: a sandboxed scenario has the service and nothing else on the far side of a forwarded port.

The showing is twelve seats and nothing refills it, so a scenario that needs a free seat must put
the showing back first — `DELETE /api/showing`, documented on the seat-booking API. QA drives this
service repeatedly (a rehearsal, the scored execution, a re-run after a repair), and a scenario that
assumes the pool it found the first time fails the second for having no seat left rather than for
anything this story claims.
