### `stale-citation` — the code under this citation changed after it was last read

This finding is not a defect in the book's grammar. Every bullet here parsed, every link resolves,
and `doctor` is green on this node. What is stale is the *claim*: the node cites a file whose
contents have changed since this citation was last stamped, and nothing in the node's text has
been re-read against the new bytes.

The context names the changed file (`"file"`), the nodes citing it (`"nodes"`), and, per node, the
exact `code:` target string it cites (`"citations"`) — that target is the one this item is about;
a node's other citations, to files this item does not name, are not.

## What to do

1. **Read the cited file first, in full.** Not a diff, not a grep — the file as it is now. You are
   not reconstructing what changed; you are checking whether what the node *says* is still true of
   what the code *does*.
2. **Correct only what the source contradicts.** A node whose `does:`, `returns:`, parameters,
   effects, preconditions or `verify:` no longer match the implementation is the reason this item
   exists. A node the change did not touch — a rename, an extracted helper, a reformat — is already
   correct, and rewriting it produces churn a reviewer cannot distinguish from a real update.
3. **A claim the new code no longer supports is deleted, not softened.** If a behaviour was removed,
   its bullet and its `verify:` go with it. Leaving a check that can no longer pass is how a book
   starts failing QA for reasons that have nothing to do with the code under test.
4. **New behaviour in the same file is yours to document here**, in this node, with its own
   normative bullet and its own check from the vocabulary above. New *symbols* are not: those come
   back as coverage gaps with their own items, and inventing nodes for them from this turn's reading
   duplicates work the join is about to queue properly.
5. **Do not touch the citation itself.** Never edit the `` `code:` `` bullet's digest, and never run
   `ostler stamp` yourself — the citation is restamped automatically, against the file's current
   bytes, when this item closes `documented`. Editing the digest by hand only defeats that check.
6. If the file is gone entirely, that is a different finding and a different item will carry it.
   Say so in `doc_status` and change nothing.

Answer `complete` only when you have read the current file and every node named here describes it.
Answering `complete` without reading it restamps the citation against bytes nobody checked, which
is strictly worse than leaving the item open — the drift becomes invisible instead of pending.
