### `unspelled-alternation` — one node, two `verify:` bullets, two different answers

Two `verify:` bullets on this `interaction`/`invocation` call the same check with the same
identifying argument — the same `path=`, the same `locator=` — and a different value for
whichever argument is left. `- verify: http_status(201, path="/api/widgets")` beside
`- verify: http_status(400, path="/api/widgets")` is the shape: one node claiming the same
request both succeeds and is refused.

**This is not two checks on one scenario — it is two scenarios sharing one node.** A single
`does:`/`when:` describes one outcome, and a node can only ever be true of one of the two
values at once. The generic repair fragment has no notion of this, because the fix here is not
"correct the bullet" — it is "split the node," and the default prompt has nothing to say about
what to split it into or what a base case is.

To repair each one:

1. **Pick the base case.** Usually the `when:`/`does:` already reads as the ordinary path — the
   accepted request, the enabled control — and its `verify:` keeps the value that belongs to it.
   That node keeps its own id and its `on:`/`trigger:`/`role:`/`name:`/`keyboard:` bullets.
2. **Give the other outcome its own node, linked by `extends:`.** Add a sibling
   `interaction`/`invocation` — name it for what it does (`refuse-<base>`, not `<base>-2`) —
   with `- extends: [<base case>](#<anchor>)` and nothing else in the control-identity bullets.
   `extends:` inherits `on`/`trigger`/`role`/`name`/`keyboard` from the node it names, so
   repeating them on the arm is redundant rather than required.
3. **Move the differing `verify:` onto the arm it is true of**, and give the arm its own
   `when:`/`does:` describing the branch that produces that value. Each node's `verify:` bullets
   should now agree with each other — the split is complete when neither node still carries a
   check that contradicts one of its own siblings.
4. **Do not just delete one of the two `verify:` bullets.** Both outcomes are real and both need
   coverage; deleting one only hides the second scenario instead of giving it a node to live on.

If more than two values collide on the same check and argument, that is more than two
scenarios, not one alternation — give each value its own arm extending the same base case,
rather than trying to fit three outcomes through one `extends:` pair.
