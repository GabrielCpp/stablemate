### `precondition-discharged-by-arrangement` — a `when:` with no check, and none is owed

This `interaction`/`invocation` arm's `when:` — the finding's `message` quotes it — declares no
`verify:`, and the compiler is telling you that is correct as written. `when:` states the
condition under which the arm's other claims hold; it is not itself something a user or a
downstream service could observe going right or wrong, so there is nothing for a check to prove.
**Do not add a `verify:` under this bullet to silence the finding** — a check written against a
condition rather than a claim has no state in which it could fail, and a check that cannot fail
is not evidence of anything.

The finding still exists because the same words can describe two different things, and only one
of them belongs here:

- **A genuine condition** — "the cart is non-empty", "the user is signed in", "`quantity` a
  positive integer". Nothing to do. Leave the bullet exactly as it is; the arm's `arrange:` or
  `fixture:` bullets (if any) are how the book makes that condition true before the arm runs, not
  how it gets checked.
- **An observation wearing a `when:` label.** If what is written is actually a claim about what
  the node *does* under some circumstance — "returns the cached page on the second request", "the
  retry counter resets after a success" — it was misfiled. Restate it as its own `does:` or
  `states:` bullet, with its own `verify:` directly beneath it, the same way any other claim on
  this node is checked:
  ```markdown
  # misfiled — a claim about behavior, filed as a precondition
  - when: the retry counter resets after a success

  # refiled — the claim moved to a bullet a check can attach to
  - does: resets the retry counter after a success
  - verify: json_path(path="$.retries", equals=0)
  ```

If the condition needs to actually hold before this arm's assertions run — as opposed to merely
being named — that is arrangement, not verification, and belongs under `arrange:` or `fixture:`
directly beneath the `when:`. A `when:` the compiler tries to arrange and cannot is a different,
separate finding, `unarranged-interaction-precondition`; this one means the compiler never got
that far, because the obligation carried no check to dispatch on in the first place.
