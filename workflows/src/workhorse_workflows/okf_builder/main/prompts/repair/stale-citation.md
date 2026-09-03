### `stale-citation` — the code under this node changed after the node was written

This finding is not a defect in the book's grammar. Every bullet here parsed, every link resolves,
and `doctor` is green on this node. What is stale is the *claim*: the node cites a symbol whose
source has been rewritten since the last run that documented it, and nothing in the node's text has
been re-read against the new bytes.

The context carries which kind of staleness it is:

- `"reason": "drifted"` — the symbol is still at `citation`, and its body is different. The digest
  pair in `evidence` is the old watermark and the current one; it tells you *that* it changed, never
  *what* changed. Read the source.
- `"reason": "moved"` — the symbol's body is byte-identical and it now lives at `moved_to`. This is
  a re-grounding, not a re-description: repoint the `code:` bullet and change nothing else. A moved
  symbol whose prose you rewrite anyway costs a turn and risks losing knowledge the old text held.

## What to do

1. **Read the cited source first, in full.** Not a diff, not a grep — the symbol as it is now. You
   are not reconstructing what changed; you are checking whether what the node *says* is still true
   of what the code *does*.
2. **Correct only what the source contradicts.** A node whose `does:`, `returns:`, parameters,
   effects, preconditions or `verify:` no longer match the implementation is the reason this item
   exists. A node the change did not touch — a rename, an extracted helper, a reformat — is already
   correct, and rewriting it produces churn a reviewer cannot distinguish from a real update.
3. **A claim the new code no longer supports is deleted, not softened.** If a behaviour was removed,
   its bullet and its `verify:` go with it. Leaving a check that can no longer pass is how a book
   starts failing QA for reasons that have nothing to do with the code under test.
4. **New behaviour in the same symbol is yours to document here**, in this node, with its own
   normative bullet and its own check from the vocabulary above. New *symbols* are not: those come
   back as coverage gaps with their own items, and inventing nodes for them from this turn's reading
   duplicates work the join is about to queue properly.
5. If the symbol is gone entirely, that is a `dangling-code-ref` and a different item will carry it.
   Say so in `doc_status` and change nothing.

Answer `complete` only when you have read the current source and the node describes it. Answering
`complete` without reading it advances this node's watermark to bytes nobody checked, which is
strictly worse than leaving the item open — the drift becomes invisible instead of pending.
