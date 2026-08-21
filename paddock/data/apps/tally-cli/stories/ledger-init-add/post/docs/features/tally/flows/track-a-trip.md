---
type: flow
slug: track-a-trip
title: Track a trip
---
# Track a trip

- start: [tally init](../tally.md#init)
- steps:
  - Create the ledger for the trip with [`tally init`](../tally.md#init), naming the currency it
    records.
  - Add what was spent, one expense at a time, with [`tally add`](../tally.md#add).
- end: [tally add](../tally.md#add)
- verify: created(subject="tally.json")
- tests:

The journey the ledger exists for, as far as `tally` goes today: one ledger, created once, that
grows an expense at a time. Nothing reads it back yet — the trip is recorded before it is totalled,
and a ledger that cannot be added to is not worth reporting on.
