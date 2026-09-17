### `unresolved-precondition` — a compiled plan cannot yet reach this obligation's state

`ostler qa`'s compiler tried to turn this obligation's `does:`/`verify:` bullets into a runnable
scenario and hit a state it could not arrange from the book alone. The finding's `message` names
which of these it was:

- **"no fixture arranged for this obligation"** — the obligation's node declares no `fixture:`
  bullet, so the compiler has nothing to call before the scenario's action. Add one, naming a
  fixture node under `docs/features/<surface>/fixtures/<name>.md` (or an existing one that already
  provides the state this obligation needs).
- **"the path still carries a template variable"** — the route path has an unfilled `{token}` the
  compiler could not bind to a produced fact. Either an earlier obligation in this scenario needs
  to arrange/produce the value the token names, or the node's `params:` needs to say which prior
  step's result fills it.
- **"the path/a verify argument references `@node.key`/`$name`, not resolvable without running the
  plan"** — the reference names a fact or capture no *earlier* obligation in the same scenario
  produces. Either the reference is misspelled/points at the wrong node, or the producing
  obligation needs to move earlier in the book's document order (the compiler resolves in that
  order, not alphabetically), or the fact genuinely does not exist yet and the node's claim is
  premature.

Read the node's source and its neighbours in the same scenario before guessing which — the
compiler already did the mechanical half (walking the document in order, matching reference
shapes); what is left is deciding what the book should have said.

The same code also covers two screen-compilation gaps `ostler qa compile-plan` raises when a
`### <component>` cannot be turned into a page scenario:

- **"carries `states:` (...); no scenario compiled for a state-scoped arrangement"** — the
  component is only present in a named arrangement (its `states:` bullet, quoted in the message),
  and the compiler has no way to force the page into that arrangement from the book alone. Either
  add a `fixture:`/`params:` bullet that puts the screen into that named state before the scenario
  asserts against it, or leave the gap — a state-scoped claim with nothing to arrange it into is
  honestly unresolved, not a bug in the compiler.
- **"trigger ... could not be compiled to a page action"** (an `## Interactions` row) — the `on:`/
  `trigger:` bullets name a component and an action, but the compiler emits a `TODO(arrange)` for
  the actual interaction rather than guessing at a Playwright call. Fill in the real click/fill/
  select call the `trigger:` prose describes.
