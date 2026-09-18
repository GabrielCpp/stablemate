### `same-as-disagreement` — a `same-as:` family states two different values for one key

A node's `same-as:` claims another node is the *same documented thing*, written a second
time — which means one fact, stated twice. This finding says the two statements disagree:
one occurrence declares a normative key (`role:`, `does:`, `states:`, …) one way, and
another occurrence of the same family declares it another way. Both cannot be true of one
thing, so something here is wrong.

Do not silence this by copying one member's value over the other's. That makes the finding
go away without settling anything — you would be guessing which claim is true, and a
guess that happens to be wrong now reads as agreement instead of as the open question it
was.

- **Read the cited source for each declaring member** — the `code:` grounding, the
  screenshot, the spec the node is documenting — and decide which value the thing actually
  has. Fix the occurrence(s) that state the wrong one so every declaring member agrees.
  A member that omits the key entirely is not part of the disagreement and needs no edit.

- **If the two occurrences genuinely make different claims** — one screen's control really
  does render with a different role, or a different state, than the other's — they are not
  the same documented thing, and the `same-as:` bullet is what is wrong, not the values.
  Remove the `same-as:` claim (both directions — see `one-way-same-as`) rather than forcing
  two different facts to share one family.

Never resolve this by deleting the disagreeing bullet outright to make the finding
disappear. Deleting it raises nothing at all — which is the problem: a claim the book used
to make becomes a claim nobody is held to, and the QA obligation packet stops minting an
obligation for it. That is strictly worse than the open finding you started with, because
nothing will report it again. Delete a bullet only when the thing genuinely makes no such
claim.
