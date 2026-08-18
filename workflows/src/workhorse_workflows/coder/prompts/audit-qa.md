---
agent: agent
---

# Independently Try To Refute A Candidate QA Pass

The runner reported `passed`, the execution reviewer confirmed that the objective was reached,
and the deterministic evidence gate validated its artifact contract. Treat the plan and evidence
as frozen and independently try to refute the candidate pass. Do not execute the product, edit the
plan, request exploration, or author replacement evidence.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Gated status: `{{ workhorse_var('qa_status') }}`
- Gate notes: `{{ workhorse_var('qa_notes') }}`

Read all of:

- `qa_plan.py`;
- `qa/qa-run.ndjson`;
- `qa/run-manifest.json`;
- the story acceptance criteria; and
- every artifact you choose to rejudge from the current manifest.

## Coverage is computed — read the map, do not re-derive it

Coverage is exhaustive and deterministic, and it is **already joined**. Run it from the spec
directory:

```bash
ostler qa evidence-map                     # every obligation, worst status first
ostler qa evidence-map --status uncovered  # one status at a time
```

It joins `qa-okf-context.json` × `qa/qa-run.ndjson` × `qa/run-manifest.json` ×
`qa-evidence.json` and returns one row per obligation carrying `status`, `why`,
`checksDeclared` / `checksObserved` / `checksMissing`, `claimedBy`, the passing and failing
assertion counts, `logRefs`, and the `evidence` files. **Do not reconstruct that join by
reading the four files against each other.** It is arithmetic the tooling did, a set
difference does not run out of budget or hold an opinion, and a coverage claim you re-derived
by hand disagrees with the one the flow gates on.

Route on `status` rather than judging it:

- **`covered`** — passing assertions are bound to it and every check its `verify:` bullets
  declare was actually made. Nothing to file; this is not where refutations come from.
- **`claimed-but-unasserted`** — a scenario named the obligation in `covers` and no passing
  assertion backs it, or `checksMissing` is non-empty: the plan claimed a declared check it
  never invoked. `evidence-defect`, and the repair is the missing assertion, scoped by where
  it lands.
- **`uncovered`** — nothing claimed it at all. `plan-defect`; the repair is a scenario.
- **`contradicted`** — the ledger and `qa-evidence.json` disagree, or a bound assertion
  failed under a published pass. Refute it and quote both sides from `why` and
  `failingLogRefs`; this is the one status that is never a judgement call.

An obligation whose row reports no `checksDeclared` is a hole in the *book*, not in the run:
nothing downstream could bind it, so any assertion satisfied it. Say so in `notes` — the
repair is a `verify:` bullet, which belongs to the documentation gate and not to this story's
QA plan — and do not refute the pass on that alone.

With the map read, spend the pass on what it cannot compute: sample the riskiest evidence for
qualitative refutation — persistence/reload, event consumers, concurrency/idempotency, state
isolation, journey completion, visual state, recording continuity, and error handling — and
judge clause partiality on the story's acceptance criteria, which carry no `verify:`
declaration and so appear in no set difference. An AC promising three things whose scenario
proves one is a `plan-defect` the map will call `covered`.

For every impacted flow, verify that evidence begins at the documented start instead of
deep-linking past navigation, reaches the documented end, and contains no hidden 5xx/crash/console
error.

Use machine-readable evidence for geometric/textual claims. Never invent fields or values
that do not exist in the ledger/artifacts. A runner pass is refuted when evidence shows a
real contradiction, a partial journey, or an assertion that does not prove its `covers`
claim.

## Judge the layout, not only the assertions

Every screenshot has a `<name>.layout.json` beside it (`schema: browser-layout/1`, or
`device-layout/1` when the screen was measured from a phone's view hierarchy instead of a
DOM): the viewport, the laid-out document size, and each structural region's box as a share
of the viewport. **Read it for every screenshot in the manifest.** It exists because a browser
assertion cannot see a broken page — `by_role(...)` finds an element in the accessibility
tree whether the page lays it out across the window or crushes it into a column against one
margin, so a scenario proving every element is present passes over a page no user could use,
and the screenshot that shows it is the one artifact nothing downstream reads.

On a viewport at least 900px wide, refute the pass as `product-contradiction` when:

- the primary content region (`main`, `article`, or the region carrying the page's body copy)
  has `viewportWidthShare` below 0.4 and no sibling content region occupies the rest — the
  page rendered as a narrow column, whatever its text says;
- that region's `startsRightOf` is above 0.5 while nothing occupies the left half — content
  pinned against a margin;
- `flags` is non-empty: `horizontal-overflow` means the document laid out wider than the
  window, `region-starts-off-screen` means a region begins past the right edge. Neither
  involves a threshold; both are defects.

A `device-layout/1` digest has no laid-out document distinct from the screen, so its `flags`
list is always empty and `horizontal-overflow` is not evidence of anything there. Judge a
device screen from the vet report below and from region shares, never from a missing flag.

Scope those findings `product-test` — the repair is CSS or markup in product code — so the fix
loop repairs them inside this story rather than the run rediscovering the same page next time.
Quote the measured numbers in `issue`; a layout finding without them is unactionable.

A browser scenario that took no screenshot has no layout evidence at all. That is a `plan`
finding — the repair is a `qa.screenshot()` in `qa_plan.py` — and it does not by itself refute
a pass whose assertions are otherwise complete.

Where `qa.vet` ran there is also a `<name>.vet.json` beside the screenshot
(`schema: vet-placement/1`): each documented component, the box it actually occupied, and
whether that agrees with the `placement:` band the book gives it. Read it first — it is the
book's own verdict, and a `misplaced` or `missing` verdict is a defect stated in the terms the
component was documented in, not a threshold you had to pick. The thresholds above remain the
floor for a screen whose components the book has not placed yet; when a vet report covers the
screen, quote its verdict rather than re-deriving one from the digest.

Return `stands` only when no concrete refutation survives. A refutation must be classified:

- `plan-defect`: the frozen plan did not actually test a required objective;
- `evidence-defect`: the claimed proof is missing, stale, incoherent, or does not support its
  coverage claim; or
- `product-contradiction`: current evidence directly demonstrates behavior contrary to the
  claimed pass.

The auditor never repairs or extends QA. It may not upgrade any result or turn a plan/evidence
defect into a product claim.

Append `## Independent Audit` to `<spec_dir>/qa.md`, naming the obligations and evidence
sampled plus any concrete refutation. Append below the existing content and leave the `---`
frontmatter block intact — it carries the `type:` that makes the doc an OKF Concept.

Return JSON only:

```json
{
  "status": "",
  "verdict": "refuted",
  "refutation_class": "evidence-defect",
  "findings": [
    {
      "id": "A1",
      "scope": "product-test",
      "target": "`AC9` / scenario `export-draft` / `editor-shell.browser.test.tsx`",
      "issue": "AC9 claims no network call during export; the only proof is a static read of `exportDraft()`.",
      "repair": "Add a fetch-spy assertion around the export action asserting zero requests."
    }
  ],
  "notes": "Coverage is complete except for AC9, whose no-network clause is never exercised."
}
```

`verdict` is exactly `stands` or `refuted`. `refutation_class` is `none` only when the pass
stands; otherwise use one of the three classes above with concrete scenario, assertion,
obligation, and artifact references.

A refutation — and a `stands` that still names a refutation class — must carry at least one
finding, each with `id`, `target`, `issue` and `repair`. `notes` summarizes them; `findings`
is what the repair is briefed from. `id` is any stable handle; reuse the same one when you
restate a finding across passes. A pass that stands cleanly returns an empty list.

Every finding names its `scope`, and the flow routes on that field rather than on your prose.
The question the scope answers is **where the repair lives**:

- `plan` — the repair is an edit inside `qa_plan.py` / `qa-plan.md`. Sent to the plan author.
- `product-test` — the repair is an assertion, fixture or fix in product code or a committed
  test the plan only cites. Sent to the fix loop, which edits the code.
- `stack` — the repair is in `qa-stack.yml` and the workflow's `ensure_stack` step: a service,
  emulator, database, seed or aggregate command that must be up before the plan runs.

Name the scope by where the repair lands, not by which gate found it. An evidence defect
whose real repair is a missing test assertion is `product-test`, not `plan`: filed as `plan`
it bills a replan that cannot write the assertion, and the identical gap comes back on the
next pass. Classifying it honestly is what makes the refutation actionable rather than a
finding the run rediscovers until its budget runs out.

### `status` — how you say you cannot judge this at all

Leave `status` empty on any turn that reached a verdict, however unwelcome. Set it to
`"blocked"` **only** when nothing in this repository would let you reach one, because what is
missing is external to it: a credential or deployment you cannot perform, a product decision
present in neither the story nor the plan, or work that lives in another repo. A `blocked`
turn ends the loop and hands the story to an operator, so it must name that specific
dependency in `notes` and say what you attempted before concluding it. A hard judgement is
not a blocked one — the fields above exist to carry an unfavourable verdict, and reaching for
`blocked` to avoid picking one takes the decision away from the only stage allowed to make it.
