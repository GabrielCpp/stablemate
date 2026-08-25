### `unminted-claim` — a bullet asserts behavior from a key that mints no obligation

The bullet reads like a claim — "must", "always", "is validated", a concrete behavior —
but it sits under a key this node type mints no QA obligation from. Nothing will ever
prove it: the doctor's obligation walk skips it, no scenario cites it, and a reader who
trusts it is trusting an unverified sentence. The finding names the normative keys the
type *does* mint from; those are the two destinations, and choosing between them is a
fact about the code, not a wording preference:

1. **Open the node's `code:` targets and find the claim in the source.** Does the code
   actually enforce it — a validation branch, a guard, a constraint the tests could
   observe? Then it is a real obligation filed under the wrong key: **move it under one
   of the normative keys the finding lists**, worded so it mints cleanly (one claim, one
   bullet — do not fuse it into an existing bullet and trade this finding for a
   `compound-normative-bullet`).
2. If the code does *not* enforce it — it is background, intent, or a description of how
   something happens rather than a promise that it must — then it is prose: **fold it
   into the node's body text**, dropping the imperative wording so it no longer reads as
   a promise nobody keeps.
3. If the source shows the claim is simply **false** — the behavior described does not
   exist — delete it and say so in your report; a wrong claim promoted to a normative key
   is strictly worse than the warn you started with.

Never resolve this by softening the wording in place ("must" → "should") so the detector
stops firing. The bullet either becomes an obligation someone can prove or becomes prose
that promises nothing; a claim laundered into vagueness is the one outcome worse than
leaving the finding standing.
