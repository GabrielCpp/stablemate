---
type: spec.executive
---

# Executive Summary: Render the Seat Map

Stands up the seat-booking service itself and its two read surfaces: the JSON seat map at
`GET /api/seats` and the server-rendered page the service serves on `/`. Both read the same ledger
through the same function, so the page and the API cannot disagree about what is free. `GET /healthz`
lands here too, because everything waiting for the stack to come up waits on it.

Twelve seats — rows `A`-`C`, numbers `1`-`4` — all free. Nothing in this story mutates a seat.

Single service (`app`, Python stdlib), no cross-service coordination. See `plan.md` for the
implementation shape and `plan-context.json` for the machine-readable service manifest.
