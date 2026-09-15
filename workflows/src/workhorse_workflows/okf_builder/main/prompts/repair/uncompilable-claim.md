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

A `uncompilable-claim` gap never gets static credit for having "passed" — the compiled scaffold is
a `TODO(arrange)` and nothing runs in its place until the book or the harness changes.
