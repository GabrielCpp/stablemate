### `unchecked-availability-state` — the book says the user cannot act, and nothing observes it

A `states:` bullet on this node says the control cannot be used — `disabled`, `greyed`,
`read-only`, `inactive` — and no `actionable(...)` or `inert(...)` call anywhere in the book
names that node. `states:` mints an obligation, so this is a claim the book makes and nothing
can ever prove or refute.

**`visible(...)` is not the check for it.** A greyed-out button is on the screen and reads the
right label, so a `visible(...)` bullet aimed at it goes green in exactly the state this claim
is about. That is why the finding exists: the weaker assertion is already available, already
passing, and already reported as coverage.

To repair each one:

1. **Write the claim as what the user can do**, on the node that carries the claim or on the
   screen/interaction the state belongs to, pointed at the control's own anchor:
   `- verify: inert(locator="#submit-button")` for a control that must not accept the action,
   `- verify: actionable(locator="#submit-button")` for one that must.
2. **The state is a precondition, not part of the check.** `inert(...)` observes the control
   in whatever state the scenario arrived at, so the bullet belongs where the book says that
   state holds — under the claim describing it, not floated to the top of the node.
3. **Do not name the attribute.** `disabled` is HTML's spelling; a mobile surface says
   `enabled=false` and an API says nothing at all. A check named after one rendering's
   attribute is compilable by one driver and meaningless to the other three, which is why the
   vocabulary has `actionable`/`inert` and no `attribute(...)`.
4. **Do not delete the `states:` bullet** to clear the finding. The state is a real fact about
   the control; what is missing is the observation. Deleting the claim removes the coverage
   the check was owed, silently.

If the control genuinely has no anchor to point at, declare the `component` — a claim about a
control the book never declared is the book telling you a node is missing from it.
