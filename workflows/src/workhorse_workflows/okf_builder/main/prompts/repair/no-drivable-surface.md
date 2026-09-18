### `no-drivable-surface` — `driver:` cannot perform against any of `surfaces:`

`driver:` says who carries out the runbook's steps; `surfaces:` says what is stood up. This
finding means the two disagree: the driver's family can only ever exercise certain node
types — `web` and `mobile` a `screen`, `http` a `server`, `cli` a `cli` — and none of the
nodes `surfaces:` resolves to is one of them. A browser driver pointed at a `surfaces:` list
whose only entry is a `type: server` node is exactly this: nothing a browser could open.

This usually happens when a runbook is scaffolded from another app's template and only
`surfaces:` gets updated for the app at hand — `driver:` is left at whatever the template
shipped, and the two bullets stop agreeing.

To repair it, read what the runbook actually boots and decide which bullet is wrong:

1. **`surfaces:` is incomplete.** The stack really is driven the way `driver:` says, but the
   runbook never links the node a walk would open. Add the missing `screen`/`server`/`cli`
   node to `surfaces:` — the one whose route or endpoint the driver actually exercises, not
   every node the stack happens to expose.
2. **`driver:` is stale.** The stack this runbook brings up is exercised the way its
   `surfaces:` already say — an API stack with only `server` nodes wants `driver: http`, not
   `driver: web`. Fix `driver:` to the family that matches what `surfaces:` actually names.

A runbook that declares no `surfaces:` at all is reported the same way, and repairs the same
way: it names a performer and nothing for that performer to exercise, so add the node the
runbook's steps actually drive.

Do not silence this by deleting `surfaces:` or by picking a driver value at random to make
the mismatch disappear — a runbook with the wrong driver dispatches the wrong kind of QA walk
at bring-up time, which fails for a reason that has nothing to do with the product.

`driver: artifact`, `driver: iac` and `driver: none` are never held to this check — none of
the three names a node type this vocabulary exercises, so a mismatch is not possible for them
and this finding never fires on one. If a runbook using one of those three drivers is still
reported here, that is drift in `ostler` itself, not something to repair in the book.
