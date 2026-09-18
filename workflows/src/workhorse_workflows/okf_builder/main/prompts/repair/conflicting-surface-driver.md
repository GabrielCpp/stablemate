### `conflicting-surface-driver` — two `walkthrough: true` runbooks disagree about one surface's `driver:`

A `runbook` node's `driver:` states what *that runbook* drives. Several runbooks covering
one surface with different `driver:` values is the ordinary shape of a real service — a lint
runbook, a browser runbook and an IaC runbook can all be correct about the same code — so
the book names the one that is *how the surface is exercised* by marking it
`walkthrough: true`. This finding means two runbooks both make that claim and still state
different `driver:` values. That is not a detail either reader can shrug off: `driver:` is a
grammar selector, not a label. The route grammar reachability is computed in and the
value-kind grammar a node's bullets are held to both need exactly one answer per surface, and
two marked runbooks naming two different drivers leaves neither question answerable — so both readers treat the surface as if it declared no driver at all until this
is settled, which quietly widens what every one of that surface's screens and components is
allowed to say. QA stops too: D1's dispatch table decides what performs a step from the
surface's `driver:`, so while two are stated every obligation on this surface compiles to a
gap instead of a check. Nothing this surface claims is observed until the runbooks agree.

This usually happens when a second runbook is added for the same service — a dev-local way
to bring the same thing up alongside the one already documented — and the new file's
`driver:` is copied from whatever template it was scaffolded from rather than checked
against what the surface's other runbook already states.

To repair it, read every runbook the finding names and decide what actually performs
against this surface:

1. **The runbooks describe the same way of standing the surface up**, and one of them has
   the wrong `driver:` — a copy-paste from a template, a stale value nobody updated. Fix the
   wrong one so both agree.
2. **The runbooks describe two genuinely different ways of exercising this surface** — a
   deployed stack reached over HTTP and a dev-local CLI wrapper around the same service, say.
   Both `driver:` values are individually correct, and the surface can still only be walked
   one way. Decide which one a QA walk against this surface actually performs, and leave
   `walkthrough: true` on that runbook alone. The other file keeps `surfaces:` and keeps its
   own `driver:` — both are true claims about what it operates on and what it drives — it
   simply stops claiming to be the walkthrough. Do **not** strip `surfaces:` to settle this:
   that bullet is the only join recording which code a runbook covers, and deleting it trades
   an ambiguity for a lost fact.

Do not silence this by deleting one runbook's `driver:` bullet to make the finding go away.
`driver:` is a **required** bullet on `runbook` — deleting it trades this finding for
`missing-required-bullet` on that same file, and the surface is still left with no settled
grammar in between. Do not pick one value at random either: a driver decided by chance rather
than by what the runbook's `## Steps` actually launch dispatches the wrong kind of QA walk at
bring-up time, which fails for a reason that has nothing to do with the product.
