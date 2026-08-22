---
type: concept
slug: ledger-file
title: The ledger file
---
# The ledger file

- code: tally/ledger.py::save
- code: tally/ledger.py::load
- extends:
- persistence: ledger-file — a command that changes the tally has written the whole ledger before it exits, so
  the next process reads back exactly what the previous one left.
- consistency: ledger-file — the file is one JSON object, with a `currency` string and an `entries` array.
- consistency: ledger-file — a reader never observes half a ledger — a write goes to a temporary path and is
  renamed over the file.

The ledger file — `tally.json` in the working directory, or whatever `--file` names — is the
whole of the product's state. There is no database and
no second copy, which is what makes the two rules above load-bearing rather than tidy: an append
that failed halfway leaves a document no command can parse, and the caller has nothing to restore
it from.

Whole-file rather than append is also why every write is a read-modify-write. Two `tally` processes
racing on the same directory is not something this file defends against; the atomic rename means the
loser's work is missing rather than that the ledger is broken, and a missing entry is a thing a
person can notice.
