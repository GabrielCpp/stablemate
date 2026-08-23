---
type: runbook
slug: seat-booking-qa-stack
title: QA stack
---
# QA stack

- driver: web
- surfaces: [Seat booking API](../http/seat-booking-api.md)
- entry-url: http://localhost:18083
- health-path: /healthz
- identity: `"status": "ok"` — a substring of the response *body*, not a host:port
- reuse: never
- boot-timeout: 60

`reuse: never`, not the `always` a stock fixture stack would take. `always` adopts whatever is
already answering `/healthz` with the identity marker — and between two replays that is the
*previous trial's* container, serving the previous trial's bind-mounted `app/`. The seeded
defect would then not be in the service under test at all, and the trial would score a clean
miss for a reason no report could show. The stack is code-dependent here by construction:
`./app` is bind-mounted, so adoption is never safe.

`--force-recreate` and deliberately **no** `down -v`. Recreating is what picks up the
bind-mounted `app/` of *this* trial rather than the container a previous one left running.
Destroying the volume here is a different thing entirely, and it is wrong: a bring-up is not
once per trial. `ensure_stack` runs at the head of every plan lane, so a story that takes more
than one lap gets its stack re-launched *while it is being observed* — and the book's
`persists` obligation is proved by confirming a booking, restarting the service and reading it
back. A `down -v` landing anywhere in that window empties the ledger and the booking is gone,
which the evidence map records as `contradicted` on a durability the product actually has.
That false contradiction was observed, and it is expensive: it scores against a defect the
trial never seeded.

So the ledger is reset at the two layers that own it, neither of which is here: the harness
drops the volume once per trial (`benchmarks/replay.py`, before the run starts), and a scenario
that needs a fresh showing asks for one over the documented route, `DELETE /api/showing`.

## Steps

### serve

- kind: service
- run: docker compose -f compose.yml up -d --force-recreate --wait
- health: curl -sf -o /dev/null http://localhost:18083/healthz
