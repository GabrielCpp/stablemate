### `duplicate-bullet` — a component carries more than one `role:` or `name:` bullet

A component is one control, and one control has one role and one accessible name. Two
`name:` bullets on the same node is a malformed node, not two claims: doctor cannot say
which one the collision check should read, so it skips the node in `collisions` until it
is well-formed. This is the shape a book defect takes when someone renamed a control and
added a bullet instead of editing one — the finding it *would* have received is
`ambiguous-locator` against some neighbour, and that finding was wrong about which side was
at fault.

To repair each one:

1. Open the source at the node's `code:` targets and read the rendered element: its
   `aria-label`, its visible text, its `role` attribute or the element's implicit role.
   That is the name and role the control actually has.
2. Keep the one bullet the source supports and delete the other. If neither bullet matches
   the source, correct the surviving one to what the source says — the source is the
   observation, the book yields.
3. If the two bullets describe two controls, the node is two components: split it, each
   with its own `code:` target, rather than choosing between the names.

Never keep both by rewording one into a `unique-by:` or a `verify:` — that converts a
malformed node into a false claim. If the source does not settle it (the name is computed
and the computation is not in reach), keep the bullet the surrounding prose describes,
delete the other, and say in `doc_status` which one you kept and why.
