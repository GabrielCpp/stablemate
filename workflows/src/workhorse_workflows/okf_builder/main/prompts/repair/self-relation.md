### `self-relation` — a relation bullet pointing at its own node

A relation is between two things. This bullet's link resolves to the very node it is
written on, so there is no second thing for the relation to hold between. It is not an
under-specified claim to be filled in later — it is ill-formed, and every reading of it is
false: a node is not a detail of itself, and `exclusive-with:` pointing home says the node
rules itself out.

The finding's `ref` names the node, the key, and which occurrence of that key — fix that
one bullet, not every bullet under the key.

Open the node and work out what the bullet was *meant* to say. Almost always one of:

- **A link that was never repointed.** The bullet was copied from a sibling page, or the
  node was split out of the page it still links to, and the href kept naming the page it
  now lives on. Point it at the node the relation actually holds against.
- **A link written without an anchor.** `- detail: [x](x.md)` on a node inside `x.md`
  resolves to the file's own root node. If the intent was a *part* of this page, write the
  anchor: `- detail: [x](x.md#the-part)`. If there is no such part, there is no relation.
- **Nothing.** The key was scaffolded empty, and something filled it with the nearest link
  to hand. Delete the bullet. An absent relation key asserts nothing; a self-pointing one
  asserts something false.

Do not leave it standing on the ground that it is harmless. A self-reference looks like a
satisfied relation to everything that walks the edge, so a consumer that clears a group
when one member adjudicates another can be cleared by a member adjudicating itself — the
book stops being checked and nothing says so.
