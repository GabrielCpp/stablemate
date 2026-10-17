---
type: spec.executive
---

# Executive Summary: Load a Trip's Expenses From a CSV File, Twice if Need Be

Adds `tally import`, which takes the file somebody else exported and puts what it holds into
the ledger.

Both criteria that matter are about the second run, because the second run is the normal one.
A file with a bad row is refused whole — exit `2`, nothing written, and the message naming the
1-based line — because a partial import leaves a ledger that is neither the old one nor the new
one and the caller cannot tell which rows landed. And an import that already succeeded is
re-run by people who did not read the message, so `import` adds the rows the ledger does not
already hold rather than the rows it was handed. Without that, "just run it again" doubles the
trip and the totals are wrong in a way nobody can see without counting.

The identity of an expense is the whole of it: who, what, how much, which day. A file that grew
by three lines adds three entries; the same file twice adds them once.

No new dependency and no new surface — two changed modules. See `plan.md` for the shape and
`plan-context.json` for the service manifest.
