### `unarranged-state` — a named arrangement has nothing to put the component into it

A `states:` bullet on this node names an arrangement — `loading`, `empty`, `error` — and mints
its own obligation, separate from the node's other claims. `states:` is declared on a
`component` node, and that component's surface can dispatch to any of the compiler's builders
(a page, a CLI tool, an HTTP endpoint) — this gap fires the same way regardless of which. The
compiler tried to give that obligation a dedicated scenario and could not: the finding's
`message` quotes the arrangement and names what is missing, one or both of:

- **"no check declared"** — nothing under this obligation says what proves the component is in
  that state. Add a `verify:` bullet naming the check (`visible(...)`, `actionable(...)`,
  whichever the state actually changes) directly under the `states:` bullet it belongs to, not
  floated up to the node's other claims — a state-scoped claim is checked in its own scenario,
  and the compiler only ever sees the obligation this one bullet minted.
- **"no fixture arranged"** — nothing puts the component into that state before the check runs.
  Add a `fixture:` bullet naming a fixture node under `docs/features/<surface>/fixtures/<name>.md`
  that provides the state's prose (or an existing fixture that already provides it), scoped to
  this same `states:` bullet.

Both missing at once means the claim is pure prose so far — the book named an arrangement it
never told the compiler how to reach or how to recognize.

**This is not the same gap as `unresolved-precondition`.** That code is a scenario the compiler
could not finish arranging once it had already started down a page. This one is a `states:`
bullet that never got dispatched into a scenario at all — the arrangement stands entirely alone,
and until it carries both a check and a fixture, the compiler will keep gapping it rather than
guessing at either.

Do not delete the `states:` bullet to clear the finding, and do not satisfy it by widening an
existing `visible(...)` check on the node's default arrangement — that check runs in the default
scenario, not this state's, and proves nothing about the arrangement this bullet names. The
state is a real fact about the component; what is missing is the arrangement and the observation
that go with it.
