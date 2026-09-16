### `unknown-bullet` — a bullet written where its node type mints nothing from it

The finding names a key that exists in the book's grammar but is not one this node's `type`
declares. That is not the same defect as a typo or a stray bullet: the key is real, spelled
correctly, and does something on other node types — it is simply inert here. Nothing on this node
orders it, grades it, grounds it, or binds a `verify:` to it. The doctor message's own
parenthetical names which keys this node type *does* mint claims from (or says it mints none) —
read that before choosing a repair.

**This is not the "never remove a claim" rule from above.** An inert bullet carries no claim to
begin with — nothing downstream was reading it — so demoting or relocating it removes nothing the
book was asserting. Deleting a bullet that *does* carry a live claim because it happens to sit on
the wrong node type is the violation; recognizing that this particular bullet never minted one is
the repair.

Two outcomes, decided by where the claim actually belongs:

1. **The node type mints nothing at all** (the message's parenthetical reads "none"). A `concept`
   is the common case: it states no obligations, so a `verify:` or `does:` written on one can never
   bind to anything, no matter what it says. Move the sentence into the node's own prose, under the
   heading it already sits in, and delete the bullet. The information survives; only the bullet
   that could never be read survives leaving.
2. **The node type mints a different key that carries the same claim.** Move the claim to a node
   whose type does mint that key — the `endpoint`, `interaction`, `component`, or whichever type
   actually declares the observation — rather than leaving it stranded where nothing reads it.
   Link back to it if the original node needs to reference where the claim now lives.

Do not invent a third path. Aliasing the key onto this node type, or adding a doctor-suppressing
comment, re-blesses a spelling the grammar deliberately does not admit here — the finding exists
because the grammar already drew this line once.
