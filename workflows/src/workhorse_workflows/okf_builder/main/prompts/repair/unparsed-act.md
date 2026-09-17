### `unparsed-act` — an `arrange:` value is not an act this repo can perform

An `arrange:` bullet is a **performance**, carried out on this node's own surface by whoever
performs the step: `fill`, `click`, `press`, `select`. The rendered act vocabulary above is
the whole list, names and argument names both, and doctor parses every value against it.

The message says which shape this value had:

1. **A bare name — `widgets-on-hand`.** That is a *fixture*, and it is well formed; only the
   key is wrong. Move it to `fixture:`. A fixture arranges the world *beside* the surface — a
   seeded database, a stopped service — and it is the right key whenever something other than
   the performer can establish the state.
2. **A known act with wrong arguments.** The suggestion carries that act's signature. Every
   argument is a **string**, because an act's arguments are what the performer types or points
   at: `fill(locator="#quantity-field", value="3")`, never `value=3`.
3. **A name no act declares.** Pick from the vocabulary by what the state needs, not by what
   the UI looks like. If no act can establish it, the state is not reachable from this surface
   — which is a `fixture:`, or a claim that needs a different arrangement entirely.

**Write one act per bullet, above the claim it arranges.** `arrange:` binds by document order
exactly as `verify:` does: the bullets under a `when:` arrange *that* arm, and an act written
under the wrong claim arranges the wrong thing silently.

Do not repair this by deleting the bullet. The claim above it states a precondition; with no
arrangement, a compiled scenario walks into the step with that precondition false and the
run fails somewhere else entirely, against a book that was right.
