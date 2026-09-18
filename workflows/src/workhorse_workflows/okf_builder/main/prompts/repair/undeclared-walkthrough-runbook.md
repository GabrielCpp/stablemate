### `undeclared-walkthrough-runbook` — several runbooks cover one surface and none is the walkthrough

A `runbook` node's `driver:` states what *that runbook* drives, at full-book scope, via its
`surfaces:` link — so more than one runbook can cover the same surface, and that is the
ordinary shape of a real service, not a defect: a lint runbook stating `driver: cli`, a
browser runbook stating `driver: web` and an IaC runbook stating `driver: iac` can all
correctly name one surface at once. What the format still needs, and what this finding says
the book has not written yet, is which one of them is *how the surface is exercised* — the
runbook a QA walk against this surface actually performs. That claim is made by marking that
one runbook `walkthrough: true`; this finding fires when several runbooks name the same
surface with different `driver:` values and none of them carries the mark.

This is not a detail either reader can shrug off: `driver:` is a grammar selector, not a
label. The route grammar reachability is computed in and the value-kind grammar a node's
bullets are held to both need exactly one answer per surface, and several runbooks naming
several different drivers with none marked leaves neither question answerable — so both
readers treat the surface as if it declared no driver at all, which quietly widens what every
one of that surface's screens and components is allowed to say. QA stops too: D1's dispatch
table decides what performs a step from the surface's `driver:`, so while the walkthrough is
undeclared every obligation on this surface compiles to a gap instead of a check. Nothing
this surface claims is observed until one runbook is marked.

This usually happens when a second (or third) runbook is added for a surface that already
has one — a CI/lint runbook alongside the browser one, a dev-local wrapper alongside the
deployed stack — and nobody marks either one, because before this check existed nothing
required it: the book compiled, or fell back to a driver-less surface, either way silently.

To repair it, read every runbook the finding names, and decide which one's `## Steps`
actually stand up the thing a QA walk against this surface drives:

1. **One of the runbooks is the walkthrough.** Mark it `walkthrough: true`. Leave every other
   runbook exactly as it is — its own `driver:` and its `surfaces:` link both stay, because
   both are true claims (what it drives, and what code it operates on) that have nothing to
   do with which runbook is the walkthrough.
2. **None of the runbooks is really "the" walkthrough** — they cover genuinely different
   concerns on the same surface (say, a lint pass and a deployed browser check) and a QA walk
   is not really any one of them. Pick the runbook closest to what a QA session should treat as
   standing the surface up — typically the one a human would run to see the surface working —
   and mark that one. The format needs exactly one answer per surface; there is no way to leave
   it genuinely undecided and still have QA dispatch against it.

Do **not** repair this by deleting `surfaces:` from every runbook but one. `surfaces:` is the
only join recording which code a runbook operates on — it is a true claim independent of
which runbook is the walkthrough, and stripping it from a runbook that still legitimately
covers this surface (the lint runbook, the IaC runbook) destroys that claim instead of
answering the question this finding actually asks, which is *which one is the walkthrough*,
not *which ones may keep naming the surface*. Do not mark more than one runbook either: two
runbooks both marked `walkthrough: true` that still disagree about `driver:` is a different
finding, `conflicting-surface-driver`, with its own remedy of settling which mark is right,
not restoring both.
