### `unwitnessed-check` — the sensitivity harness could not build a witness for this claim

**This is not a finding about the check. Do not weaken the check to silence it.**

`ostler qa sensitivity` measures whether a declared check can go red by synthesizing a
witness observation the call accepts, perturbing it the way a real defect would, and
re-verifying. This code says the first step failed: no witness this harness can build
satisfies the call, so **no perturbation was tried and the experiment has no result**.

The finding carries the harness's own note for each call — `no witness value can be
invented for /…/`, or `the witness this harness builds does not satisfy the call`. Read it
as a statement about `sensitivity._matching`'s reach, not about the book.

It falls hardest on the **most** discriminating patterns a book writes, because those are
exactly the ones the synthesizer cannot invent a member of:

```markdown
# unwitnessed — and stronger than anything that would be witnessed
- verify: json_path("lang", matches="^(fr|en)$")
- verify: json_path("role", matches="^ROLE_(CONTRACTOR|SUPPLIER|TENDERER)$")
- verify: json_path("updated_at", matches="^(?!0001-01-01)\\d{4}-\\d{2}-\\d{2}T")
```

Each names a closed set the product must answer from. Replacing one with a looser pattern
the synthesizer can satisfy — `matches=".*"`, a bare presence check — would make the
finding go away **and make `insensitive-check` genuinely true of the same claim**. That
edit trades a real observation for a green report, which is the one outcome this whole
book is built to prevent.

**So the repair is almost always: none.** Leave the bullet exactly as it is and move on.

Change the check only when it is wrong on its own merits — it names a field the code does
not write, or a pattern the product never matches — and then repair it against the source
the way `unparsed-check` or a failing `verify:` is repaired, because the defect is that
one, not this one. If you do change it, say why in `doc_status`, naming the claim: a
reviewer needs to see that the edit answered the source and not the warning.

This is a `warn`, never an `error`, and it does not block. A book can be finished and
correct with `unwitnessed-check` standing on it.
