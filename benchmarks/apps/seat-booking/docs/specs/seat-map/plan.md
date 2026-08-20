---
type: spec.plan
---

# Plan: Render the Seat Map

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it: the tree carries the finished service, and what runs against it is QA.

## 1. Approach

The service is Python's `http.server` with no third-party runtime dependency and no build step, so
it comes up from a stock interpreter image. The domain transitions live apart from the HTTP layer:
routes parse, call one function, and serialise, so a failing scenario names the rule rather than the
route.

## 2. Files

- `app/store.py` — the ledger: the seat vocabulary, the empty showing, atomic read/write.
- `app/booking.py` — `seat_map`, the ordered projection both surfaces read, plus the
  `Refused`/`Conflict` vocabulary the transitions to come share.
- `app/page.py` — the server-rendered document: banner, seat-map region, seat buttons, summary.
- `app/service.py` — the request handler and the three read routes.
- `compose.yml` — one service, published on 18083.

## 3. Acceptance Checklist

- [x] `GET /api/seats` answers 200 with all twelve seats in row-then-number order, each carrying `id`, `row`, `number`, `state`, `version`.
- [x] A taken seat is listed with its state rather than dropped from the map.
- [x] `/` renders one button per seat, named by the seat id alone, with the state on `data-state` and a non-free seat `disabled`.
- [x] The page's status line reads `<free> of 12 seats free`, counting only seats in state `free`.
- [x] `GET /healthz` answers 200 with `{"status": "ok"}` without reading the ledger.

## 4. QA

Every claim above is observable over HTTP or on the rendered page. There is no unit-test surface to
cite: a sandboxed scenario has the service and nothing else on the far side of a forwarded port.

The showing is twelve seats and nothing refills it, so a scenario that needs a free seat must put
the showing back first — `DELETE /api/showing`, documented on the seat-booking API. QA drives this
service repeatedly (a rehearsal, the scored execution, a re-run after a repair), and a scenario that
assumes the pool it found the first time fails the second for having no seat left rather than for
anything this story claims.
