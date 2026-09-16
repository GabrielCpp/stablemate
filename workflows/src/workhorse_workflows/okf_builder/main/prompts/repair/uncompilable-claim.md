### `uncompilable-claim` — this obligation compiles to no action at all

Unlike `unresolved-precondition` (a reachable state the plan cannot yet arrange), this obligation
gave the compiler nothing to observe — there is no candidate action, so no amount of arranging
would produce one. The finding's `message` names which of these it was:

- **"the book gives this node no `route:` to act on"** — the node has `does:`/`verify:` bullets but
  no `route:` naming what to call. Either add the route the node is actually describing, or the
  claim belongs on a different node that has one.
- **"capture `<name>` from `<source>` has no observed response to read"** — a `$.`-rooted capture
  named a JSON path to pull out of a response, but this obligation's own route is missing (see the
  route case above — fix that first, this gap usually clears with it).
- **"capture `<name>` from `<source>` names a UI locator, not a response field"** — the capture's
  source is a page element, not a JSON path, and the compiler only wires up response-field
  captures automatically. A UI-locator capture needs a `qa.capture_text(...)` call written by hand
  in the compiled scenario, or the node's `capture:` bullet needs to name the response field it
  actually reads instead.
- **any other note naming a `verify:` row's operand** — the check named an operand shape
  `ostler.qa`'s vocabulary has no compiled form for yet; read the note and either rewrite the
  `verify:` bullet to a supported check, or treat this as a harness gap and raise it rather than
  papering over it with a weaker assertion.
- **"no addressable `### <component>` owns this `visible(...)` claim"** — a screen's `verify:`
  bullet sits outside every `### <component>` heading, so the compiler has no subject to attach a
  locator to. Move the bullet under the `### <component>` it actually describes, or add that
  heading if the book never gave the claim one.
- **"surface `<name>` has no `navigation` data to address this screen by"** — the screen's surface
  is missing from the book's derived reachability map entirely, which usually means the surface
  name on this node does not match any surface `ostler qa context` computed routes for. Check the
  node's path under `docs/features/<surface>/` against the surfaces the book actually declares.
- **"no route computed for this screen"** — reachability ran for this surface but produced no route
  entry for this screen at all (distinct from an explicit unreachable listing) — usually a screen
  the graph has no node for. Confirm the screen file exists and is typed `screen`.

A `uncompilable-claim` gap never gets static credit for having "passed" — the compiled scaffold is
a `TODO(arrange)` and nothing runs in its place until the book or the harness changes.
