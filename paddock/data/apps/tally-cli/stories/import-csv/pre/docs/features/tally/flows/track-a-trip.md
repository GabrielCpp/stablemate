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
  - Add what was spent, either one expense at a time with [`tally add`](../tally.md#add) or a whole
    file at once with [`tally import`](../tally.md#import).
- end: [tally import](../tally.md#import)
- verify: count(subject="entries in the ledger", equals=3)
- tests:

The journey the ledger exists for, and the one that makes re-running safe: an import that failed
partway is re-run by running it again, which is only true because
[`import`](../tally.md#import-a-csv) adds the rows the ledger does not already hold rather than the
rows it was given. A person who reaches for `import` twice is not being careless; they are doing the
obvious thing after a message they did not read.
