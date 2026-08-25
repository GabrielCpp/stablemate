### `undeclared-obligation` — the node mints obligations and declares no observation

Every normative bullet on this node (`does:`, `when:`, `returns:`, `raises:`, `status:`, `error:`,
`auth:`, `persistence:`, `emits:`, `consumes:`, `concurrency:`, `idempotency:`, `required:`,
`default:`, `semantics:`) is one QA obligation. This node has some and declares no `verify:` at all,
so nothing downstream can bind a scenario to any of them.

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
different outcome from "unsure", and it has a sanctioned exit: a doctor waiver. Append an
entry to `docs/doctor-waivers.json` (shape: `{"waivers": [...]}`), quoting the claim
itself as the reason:

```json
{"code": "undeclared-obligation", "ref": "<the node id the finding names>",
 "reason": "no check in the closed vocabulary observes: '<the bullet's claim, quoted>'",
 "backlog": "revisit when the check vocabulary can observe it"}
```

That is a reviewable ledger entry a human can audit and revoke — strictly better than
either of the alternatives: an eternally-red warn every future round re-pays an agent turn
to stare at, or a fabricated near-miss check that stamps the node green while observing
something else. The bar for taking this exit is that you walked the vocabulary above and
can say *why* each candidate check fails to observe the claim; say that in `doc_status`
too. Never waive a bullet a check in the list *can* observe — that is the deletion rule
wearing JSON.
