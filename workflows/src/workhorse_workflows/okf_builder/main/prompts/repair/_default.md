### The finding's own remedy

No fragment is written for this code, which means the finding text is the specification: read each
one's `message` and `suggestion` in the context above and apply exactly what it asks. The mechanical
ones are casing/order (`ostler fmt` fixes them), a missing heading or section (`ostler scaffold`),
and a link whose target moved (repoint it at the node that exists — never delete the reference, and
never mint a node just to give it something to land on).

**When the context says `"grounded": true`, the finding does not carry the value.** It names what is
missing; the source says what it is. Open the node's `code:` target and read it before writing
anything.

- For a `screen`: `route:` from its route definition, `requires:` from the guard wrappers that
  enclose it, `params:` binding each `:token` in the route to the interaction that mints that entity
  — link it, that is what makes the dependency reachable.
- For a `component`/`interaction`: `role:` and `name:` come from the **rendered accessibility
  contract**, not the tag — an explicit `role=`, then `aria-label` / `aria-labelledby` / the visible
  text that would become the accessible name. An explicit `role=` overriding its tag is the case
  that matters most and the easiest to miss. `keyboard:` comes from the key handlers and `tabIndex`
  you can see.
- `role:` and `name:` are **one bare token each** — the value is fed straight into `getByRole`, so a
  justification appended to it produces a locator matching nothing. Cut the value to the token
  **and** move the explanation into the node's prose in the same edit; a repair that loses knowledge
  is a worse outcome than the finding it closed.
- `ambiguous-locator` means two controls on one screen share `role:` + `name:`. Settle which of
  three cases it is by reading both in the source: one is **mislabelled** (correct it); they can
  **never co-render** (add `exclusive-with: [the sibling](#its-anchor)` to one, and cite in prose the
  code that makes them exclusive); or they **genuinely co-render with the same name** — a real
  accessibility defect, so leave the finding standing and record what you saw. Never invent a
  distinguishing label the UI does not have.
- `unnamed-interactive` means an operable control has no accessible name. Find its label in the
  source; if there genuinely is none, the app has an unlabeled control — record that rather than
  naming it for the app.
- **`none` is a claim, not a default.** Write `- requires: none` only after reading the route module
  and seeing no guard; `- params: none` only when the route has no `:token`. An unverified `none` is
  worse than the missing bullet: the bullet reads as *unknown* and is re-queued, while `none` reads
  as *verified unconditional* and ends the inquiry for every consumer downstream.
- If the source does not settle it, **leave the bullet off** and say why in `doc_status`.
