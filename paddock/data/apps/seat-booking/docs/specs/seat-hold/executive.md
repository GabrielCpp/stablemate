---
type: spec.executive
---

# Executive Summary: Hold a Seat

Adds the first two transitions — hold and release — and the endpoints over them. A free seat can be
taken off the market, and a held seat can be given back.

The criterion worth reading twice is the narrow write: releasing one seat must touch that seat only.
A release implemented by rebuilding the map from a fresh showing looks correct from the released seat
and is wrong from every other one, so the acceptance is about the neighbours.

Single service (`app`, Python stdlib), no cross-service coordination. See `plan.md` for the
implementation shape and `plan-context.json` for the machine-readable service manifest.
