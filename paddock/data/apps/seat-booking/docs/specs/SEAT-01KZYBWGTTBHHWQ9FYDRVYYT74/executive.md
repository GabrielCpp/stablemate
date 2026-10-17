---
type: spec.executive
---

# Executive Summary: Confirm a Held Seat

The transition the product exists for, and the only one with a concurrency contract. `confirm` spends
a hold on a booking, and the per-seat `version` the hold handed back is the compare-and-swap token: a
caller quoting any other number is refused rather than served, so a hold is spendable exactly once.

The booking also has to be durable — written through the ledger before the response announcing it, and
still there after a restart. A booking that lives only in the memory of the process that answered is
not a booking.

Single service (`app`, Python stdlib), no cross-service coordination. See `plan.md` for the
implementation shape and `plan-context.json` for the machine-readable service manifest.
