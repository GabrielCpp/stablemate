### `screen-preconditions-undeclared` — a reachable screen names no arrival preconditions

`ostler qa`'s reachability pass (`reach.reachability`) walked the book's navigation edges and
found a route to this screen, but the screen's own node carries neither a `requires:` nor a
`params:` bullet. That is not the same finding as `unreachable-screen` — the graph has a path here
— and it is not silently folded into the compiled scenario either: a screen with no declared
preconditions may genuinely need none (a landing screen reachable with no state at all), or it may
be missing the bullets that say what has to be true, or present, before it can be addressed.

Read the screen and the edge that reaches it (the `leads-to:`/flow `steps:` bullet on whichever
node points here): if arriving here truly needs nothing prior — no seeded record, no prior
selection — add a `requires: none` (or this book's existing spelling for "no precondition") so the
next reader does not have to re-derive that; if it does need something, add the `requires:`/
`params:` bullets naming it, the same way this surface's other screens do.
