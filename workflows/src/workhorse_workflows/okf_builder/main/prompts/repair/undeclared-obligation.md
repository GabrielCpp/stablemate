### `undeclared-obligation` — the node mints obligations and declares no observation

Every normative bullet on this node (`does:`, `when:`, `returns:`, `raises:`, `status:`, `error:`,
`auth:`, `persistence:`, `emits:`, `consumes:`, `concurrency:`, `idempotency:`, `required:`,
`default:`, `semantics:`) is one QA obligation. This node has some and declares no `verify:` at all,
so nothing downstream can bind a scenario to any of them.

**Only a top-level `- verify:` counts.** The parser reads a node's checks off its top-level
bullets; a `verify:` indented under a `does:` sub-bullet (`  - state: …` / `    - verify: …`) is
flattened into that sub-bullet's prose and declares nothing — doctor keeps reporting "no
`verify:` at all" on a node that visibly has six of them, and three repair turns that each add
another nested one leave the count at zero. Restate each sub-bullet as its own top-level claim
and put its check directly beneath it:

```markdown
# unread — the checks are prose inside the does: block
- does:
  - state: registers one `DeleteCustomer` expectation.
    - verify: created(subject="a DeleteCustomer expectation in the mock's call registry")
  - emit: returns the typed expectation handle.
    - verify: json_path(path="$", equals="the same `*Mock_DeleteCustomer_Call` receiver")

# read — one top-level claim, its check right under it
- does: registers one `DeleteCustomer` expectation.
- verify: created(subject="a DeleteCustomer expectation in the mock's call registry")
- does: returns the typed expectation handle.
- verify: json_path(path="$", equals="the same `*Mock_DeleteCustomer_Call` receiver")
```

Repeating `- does:` is the documented way to state several claims (the ostler-okf skill's
`references/bullet-grammar.md`, "repeat the key"); the one-`does:`-block rule above is about not
scattering a *single* nested block across the node, not a ban on one claim per line.

**One check per normative bullet, in the bullets' own order.** That ordering is the only pairing the
book records, so it is what a reader uses to tell which check belongs to which claim.

The failure this item exists to prevent is the **single stamp**: attaching one `verify:` to a node
carrying six obligations. Doctor goes quiet — the node declared *something* — and five claims stay
exactly as unprovable as they were. If you write fewer checks than there are normative bullets, say
in `doc_status` which bullets you left unbound and why.

For each bullet, before you write the call:

1. Name the state of the world in which the check goes red. If the answer is "the feature is
   missing" or "the service did not start", it is a rubber stamp — choose again.
2. Ask what the *likely* wrong implementation is, not the worst one, and pick the call that
   separates it from the correct one. `ostler checks` prints the defect each call excludes.
3. If the bullet says something is created or removed, the before-state is part of the observation:
   `created(subject=…)` / `removed(subject=…)`, not a status code and a present id.

Read the node's `code:` target to answer those; the bullets alone will not tell you what the near
miss is. Where the source genuinely does not settle what an obligation asserts, leave that bullet
unbound and say so — a node that stays red is a correct outcome, a node stamped green is not.

**When the claim is real but the closed vocabulary has no observation for it**, that is a
different outcome from "unsure", and it is decided per bullet, one of two ways. Say which
in `doc_status`, naming the bullet:

- **The bullet is not an obligation.** It describes what the node is rather than claiming
  what an observer would see — a sentence that no wrong implementation could make false.
  Demote it: move the text into the node's prose, under the same heading, and delete the
  bullet. Nothing is lost; a claim nothing could falsify was never a claim.
- **The vocabulary is short a check.** The bullet is a real claim and no call in
  `ostler checks` observes it. Leave the bullet unbound, and write in `doc_status` what the
  missing check would observe and the signature it would need
  (`vocabulary: settles(subject=…, within=…) — the payout lands before the ledger closes`).
  The finding stays standing on purpose: it is the ask for that check, and the vocabulary
  grows by exactly such asks. Nothing else in the book records it.

There is no third exit. A red node whose `doc_status` says which of the two it is, is a
correct outcome; a node stamped green by a check that observes something else is not, and
so is a bullet demoted to prose because a check *could* observe it and you did not look —
that is the deletion rule wearing a paragraph.
