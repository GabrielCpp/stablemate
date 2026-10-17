---
type: spec.executive
---

# Executive Summary: Show the Register

Adds the read side: the list endpoint, the register screen over it, and the navigation region every
screen sits under.

The criterion worth reading twice is the one about navigation. Following a row's link has to open
the policy as a client route — the same screen arrives either way, so a scenario that only asserts
what it landed on passes against a full document reload, and against an implementation that reads
the previous policy's record under the new number.

Two services (`app/api`, Go; `app/web`, React), same origin. See `plan.md` for the implementation
shape and `plan-context.json` for the machine-readable service manifest.
