### `undeclared-obligation` — a normative bullet has no observation behind it

This code is raised two different ways, and the finding's `ref` says which one you are
looking at — read it before you touch the book.

- **A bare bullet key** (`path#node#key`, e.g. `docs/features/demo/api.md#post-things#verify`) —
  the whole node declares no top-level `verify:` at all. Go to **"No `verify:` anywhere on the
  node"** below.
- **An indexed obligation id** (`okf:<file>#<anchor>:<kind>:<N>`, e.g.
  `okf:docs/features/demo/api.md#post-things:status:1`) — the node
  declares checks, just not for *this* bullet: `registry.attributed_checks` bound the check meant
  for it to a different normative bullet instead. Go to **"This bullet's check landed on a
  different bullet"** below.

Both readings come from the same rule — a QA plan may only claim what it can observe — seen
from two components: doctor reading the book alone sees the node-wide case; `qa compile-plan`
sees the per-bullet case, because it is what actually tries to bind one check to one claim.

#### No `verify:` anywhere on the node

Every normative bullet on this node (`does:`, `when:`, `returns:`, `raises:`, `status:`, `error:`,
`auth:`, `persistence:`, `emits:`, `consumes:`, `concurrency:`, `idempotency:`, `required:`,
`default:`, `semantics:`) is one QA obligation. This node has some and declares no top-level
`verify:` at all, so nothing downstream can bind a scenario to any of them.

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

For each normative bullet, add a top-level `verify:` directly beneath it, using the decision
procedure below. Do **not** silence this finding by deleting the normative bullets instead — a
node with no claims left is not a node that has been observed, and the obligations the finding
names are real behavior the source still has, whether or not the book states it.

#### This bullet's check landed on a different bullet

**One check per normative bullet, written directly under it.** Document order is the binding, and
it is the binding the parser reads: `registry.attributed_checks` credits each `verify:` to the
**nearest normative bullet above it**, so where a check sits is which claim it observes. Matching
counts is not enough — six checks in a block after six claims all bind to the sixth:

```markdown
# misbound — every check is credited to `auth:`, and `does:`/`status:`/`errors:` read as unobserved
- does: stores the submitted URL under a generated slug
- status: 201 with the slug in the body
- errors: 409 when the requested slug is already in use
- auth: any signed-in editor
- verify: created(subject="a link row for the submitted URL")
- verify: http_status(code=201, path="/links")
- verify: http_status(code=409, path="/links")

# bound — each check sits under the claim it observes
- does: stores the submitted URL under a generated slug
- verify: created(subject="a link row for the submitted URL")
- status: 201 with the slug in the body
- verify: http_status(code=201, path="/links")
- errors: 409 when the requested slug is already in use
- verify: http_status(code=409, path="/links")
- auth: any signed-in editor
```

Both books declare three checks. The first one binds all three to `auth:` and leaves `does:`,
`status:` and `errors:` each raising this code with their own indexed `ref`; only the second says
what each check means and clears every one of them.

The failure this item exists to prevent is the **single stamp**: attaching one `verify:` to a node
carrying six obligations. The node-wide reading goes quiet the moment any one bullet has a check,
so this reads as done — and five claims stay exactly as unprovable as they were, each still
raising its own indexed finding. If you write fewer checks than there are normative bullets, say
in `doc_status` which bullets you left unbound and why. Do not close this finding by deleting the
unbound normative bullet either — the same warning as above applies here per-bullet: the claim is
real, and removing it does not make it observed.

#### Writing the check

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
