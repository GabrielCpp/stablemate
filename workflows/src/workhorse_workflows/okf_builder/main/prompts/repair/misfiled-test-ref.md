### `misfiled-test-ref` — the citation is right, the key is wrong

The value on `verify:` is a code or test reference: `path::symbol`, or a path ending in a source
file extension. It is not malformed — it is well formed under `tests:`, which is why it carries
its own code instead of travelling as [`unparsed-check`](unparsed-check.md).

A test id says **which code ran**. It never says **what was observed**, and the claim above the
bullet is held to the observation, not to the run. So the repair is two moves, never one:

1. **Move the citation to `tests:`.** If the node's type declares a `tests:` key, `ostler autofix`
   has already offered to do this — the finding is marked `fixable` exactly when it will. Run it
   and read the diff rather than retyping the path. A type with no `tests:` key (`screen`,
   `runbook`, `server`, `cli`, `fixture`) has nowhere to move it to: the citation belongs on the
   node the test actually covers, and if there is no such node the reference is prose, not a
   bullet.
2. **Write the observation on `verify:`.** Read the normative bullet the citation was written
   under and declare the check that would go red if that claim were false. Run `ostler checks` for
   the vocabulary and the defect each call excludes.

A finding that is *not* marked `fixable` on a type that does declare `tests:` is one ostler can
see but cannot prove — a citation inside an unbalanced code span, which a program must not rewrite
unasked. Move that one by hand.

**Deleting the bullet is not the repair.** A node that cited a test at least recorded that
something covered it; a node with neither the citation nor a check has been made green by
forgetting.
