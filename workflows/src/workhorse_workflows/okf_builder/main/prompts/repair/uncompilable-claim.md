### `uncompilable-claim` — this obligation compiles to no action at all

Unlike `unresolved-precondition` (a reachable state the plan cannot yet arrange), this obligation
gave the compiler nothing to observe — there is no candidate action, so no amount of arranging
would produce one. The finding's `message` names which of these it was:

- **"the book gives this node no `route:` to act on"** — the node has `does:`/`verify:` bullets but
  no `route:` naming what to call. Either add the route the node is actually describing, or the
  claim belongs on a different node that has one.
- **"capture `<name>` from `<source>` is declared on this node and …"** — the book asked for a
  value to be bound and the builder that compiled this obligation will not bind it. The clause
  after *and* is that builder saying why, and it is the whole diagnosis:
  - **"has no observed response here to read the field off of"** — a `$.`-rooted capture named a
    JSON path to pull out of a response, but this obligation's own route is missing (see the route
    case above — fix that first, this gap usually clears with it).
  - **"names a UI locator, not a response field, and this builder holds a response"** — the
    capture's source is a page element, not a JSON path, and only response-field captures are
    wired up automatically. Either the `capture:` bullet should name the response field it
    actually reads, or the value wants capturing on the page node that shows it.
  - **"this scenario arrives at the screen and observes what is on it …"** / **"the trigger is
    performed here, but this builder has no declared way to read a value back out of the page
    …"** — a page capture. Nothing in the book is wrong: `qa.capture_text(...)` has to be
    written by hand in the compiled scenario, or the capture moved onto a node whose driver holds
    something to read.
  - **"a journey performs its steps and asserts the flow's own claim …"** — not a defect to
    repair here at all. The step's own obligation is where its capture compiles; look for the
    same capture's fate on that node, and fix it there if it is unbound there too.
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
