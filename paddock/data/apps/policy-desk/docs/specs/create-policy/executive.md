---
type: spec.executive
---

# Executive Summary: Write a Policy to the Register

Adds the write path end to end: the JSON ledger, the create endpoint over it, the form that posts
to it, and the detail screen a successful creation lands on.

The criterion worth reading twice is that the field rules are not uniform. A vehicle VIN is asked
for under `auto` and nowhere else, a property address under `home` and nowhere else, and an
`umbrella` policy is refused outright unless the same holder already has one of the other two on
file. A validator written as one required-fields list satisfies every scenario that only ever posts
an `auto` policy.

Two services (`app/api`, Go; `app/web`, React) behind one origin: the binary serves the built
bundle and falls back to `index.html`, so every client route is also a deep link. See `plan.md` for
the implementation shape and `plan-context.json` for the machine-readable service manifest.
