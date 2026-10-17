---
type: spec.executive
---

# Executive Summary: Start a Ledger, and Record One Expense at a Time

Ships the package, the file it keeps, and the two commands that create and grow it. There is no
service, no port and no response body: what this story produces is an exit code, a line on
stderr, and the bytes in `tally.json`.

The criterion worth reading twice is that two of the five are refusals. `init` where a ledger
already exists must leave that file byte-for-byte unchanged, and an amount that is not a
positive whole number of cents must be refused with the ledger untouched. Both are cases where
the file is the only copy — there is no history to restore from, and a truncated ledger looks
exactly like a fresh one.

That is also why `--dry-run` ships here rather than later. The flag means "no write at all",
and it is enforced in the single place either command reaches the disk through, so it cannot
come to mean one thing for `add` and another for the command that gets it next.

One stdlib-only Python package, no dependencies and no install step. See `plan.md` for the
implementation shape and `plan-context.json` for the machine-readable service manifest.
