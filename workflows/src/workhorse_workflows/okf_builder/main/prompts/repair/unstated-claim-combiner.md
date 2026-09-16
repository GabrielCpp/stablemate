### `unstated-claim-combiner` — a nested claim list does not say what it is

A claim bullet with children nested under it is either a **conjunction** — the children are
parts of one effect, all of them true together — or a **disjunction** — the children are
alternative outcomes, exactly one of which happens on any given run. A `verify:` written
under the list means opposite things in the two cases, and the grammar records neither.

This matters because of where the check lands. Under a conjunction, one check observes an
aspect of the single effect and fans out across every part. Under a list of branches, the
same check was written for **one** outcome and *refutes* the others — so crediting it to the
whole list produces a green run whose every assertion is true and whose claim is false.

To repair each one, read the node and state the word in the parent bullet's value:

```markdown
- does: all
  - does: the row is removed from the list
  - does: the counter drops by one
- verify: absent(selector="#row-42")
```

```markdown
- does: branches
  - does: a valid name is accepted and the policy is created
  - does: a duplicate name is refused with a message
```

- **`all`** — the children happen together on every run. A check under the list observes the
  effect and covers all of them.
- **`branches`** — the children are alternatives. A check may not sit on the list; split the
  branches into sibling bullets, each carrying the check that is true of *it*. Expect
  `unobserved-branch` to name the ones still missing a check.

The word is a statement about the product, not a formality. If the source does not settle
which it is — read the handler, not the wording of the bullet — say so in `doc_status`
rather than picking the one that makes the finding go away.
