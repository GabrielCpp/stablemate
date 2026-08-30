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

- `qa-report.md` **first** — the runner's own per-criterion, per-obligation account of this
  run: each acceptance criterion with its verdict, the step every covering assertion ran in,
  its check, observed and expected values, and the screenshots (with their `vet` verdict) and
  files behind it; every scenario step by step; and a `## Warnings` list. Its `## Warnings`
  and every `UNPROVEN` row are where a refutation starts: a criterion no assertion covers, an
  assertion with no observed value, a scenario that stopped early. Confirm its run marker
  (`<!-- run: … -->`) names the run in `qa-evidence.json`;
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
- **`insensitive`** — every declared check ran and passed, and `checksInsensitive` says no
  observation of the product could have made any of them fail. A pass here proves the
  assertion ran, not that the product does this. `evidence-defect`, and the repair is the
  declaration — a `verify:` bullet that names what would be different if the claim were
  false — never a refutation of the app on this ground alone.
- **`unproven`** — the scenario that would have observed it did not run to completion, so
  nothing looked at the product. This is **not** a refutation and must never be filed as one:
  it is an `evidence-defect`, the repair is in the plan (a misspelled field, a step that
  raised, a timeout), and `abortedLogRefs` names the scenario that stopped. Filing it against
  the product accuses a tree the run never examined.

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
deep-linking past navigation and reaches the documented end. A flow whose obligation row is
`required` is owed that walk; a context-only one is not.

Use machine-readable evidence for geometric/textual claims. Never invent fields or values
that do not exist in the ledger/artifacts. A runner pass is refuted when evidence shows a
real contradiction, a partial journey, or an assertion that does not prove its `covers`
claim.

## Judge what the page asked the network for

Every browser scenario writes `qa/traces/<scenario>-diagnostics.json`
(`schema: browser-diagnostics/2`) beside its trace: `pageErrors`, `consoleErrors` and the full
`console` list, and `requests` / `responses` carrying each request's `url`, `method`,
`resourceType`, `status`, `durationMs` and — within a byte budget — the response body itself.
**Open it for every browser scenario in the run, not only the ones you already doubt.** It is
the record of what the product actually did while the assertions were being satisfied, and a
seeded defect that never breaks an asserted element leaves its whole trace here and nowhere
else: a list screen that renders correctly while firing one failing request per row asserts
green all the way down.

Two of these the harness already refuses on its own, so a scenario that published a pass while
carrying either is a `contradicted` row, not a judgement call — say so and quote it:

- `pageErrors` non-empty — an uncaught exception reached the window.
- any `responses` entry with `status` at or above 500.

The rest is yours to judge, and the discrimination that matters is **provoked or not**. A
scenario that submits an invalid form to prove a refusal *should* show a 4xx, and a page that
finished loading may cancel an in-flight request on the way out. Refute as
`product-contradiction`, scoped `product-test`, when:

- a `responses` entry in the 400s answers a request the scenario never provoked — no step of
  it was asserting a refusal, an absence or an unauthorized case — and most sharply when the
  same failing request repeats per row, per card or per poll tick. Quote the `url`, the
  `status`, and how many times it appears;
- a `console` entry names a product failure rather than a resource: an unhandled rejection, a
  framework error boundary, a hydration mismatch, a failed state update. Quote the message.

And do **not** refute on:

- console output alone. A clean run of the same product carries console noise, and
  `Failed to load resource: ...` is the browser narrating a response the `responses` list
  already shows you — judge the response, not its echo;
- a `failedRequests` entry with no status, which is usually a navigation cancelling its own
  pending requests;
- a 4xx the scenario's own steps asked for. Name the step that provoked it and move on.

A documented route answering a documented error is not by itself a defect either: check the
endpoint's `errors:` bullets before filing one. What makes it a defect is the caller — the
page had no business asking.

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

## Where a green scenario still fails to prove its claim

These are the plan defects this lane has actually had to send back, read off its own
history. Every one of them *runs green* — which is why the runner's pass is not evidence
against them, and why sampling the scenarios behind an obligation is the only thing that
finds one. What you find here is a `plan-defect`; quote the scenario and the step.

- **Claimed but never exercised.** `covers=` names an obligation the journey never reaches.
  The scenario passes mechanically and the obligation is untested. For every id in `covers=`,
  point at the step that actually causes the behaviour it names.
- **Half-covered clause.** The criterion says `http://` *and* `https://`, both locales, or
  "the same name after a restart", and one branch is asserted. A conjunction is covered when
  every conjunct is; a disjunction, when each arm has its own scenario or its own assertion.
- **Non-discriminating assertion.** It would pass under the very failure it claims to catch:
  an unanchored `grep -c`, a substring that also appears in the framework's *partial-failure*
  output, a helper that never checks `returncode`. Ask what would have to break for this
  assertion to go red; if the answer is "nothing this story could do", it proved nothing.
- **The evidence proves a neighbour.** The cited test exercises a different method, route or
  component than the obligation — `Put` where the obligation is `PutIfGenerationMatch`, a
  stubbed `<Outlet/>` where it is the real page. Neighbouring is not covering.
- **Negative-only proof.** Asserting an error banner is *absent* is not asserting the content
  rendered. Prove the positive claim; absence of a failure marker is not presence of a result.
- **An oracle over a field the runner never writes.** Deriving a verdict from a key that does
  not exist in the evidence the runner emits yields a vacuous pass. Only the record shapes the
  runner documents can carry an assertion.
- **The error path nobody triggers.** An obligation whose evidence is a failure response, with
  no scenario that causes the failure — no revoked token, no broken precondition, no
  conflicting write — so nothing ever observed the response the obligation is about.
- **Partial state comparison.** Checking three known objects instead of inventorying the set,
  so an extra or missing artifact passes unseen. A claim about a collection is proven only by
  inventorying the collection.
- **A terminal proof the runner cannot reach.** "Observe that the chart renders", an OCR read,
  a colour judged by eye. If no assertion in the harness can make it, it is not a proof, and
  unless `qa-plan.md` says why the claim is undecidable by the runner the obligation stands
  unproven.
- **A fixture that only works once.** It mutates shared state and passes on the first run and
  fails on the second. Every scenario must be re-runnable against the stack it just ran on.
- **Timing asserted without waiting.** A confirmation, a redirect or a background write
  asserted the instant after the action, or behind a fixed sleep chosen by trial. The proof is
  only as good as the wait before it, and that wait is an observable condition.
- **Evidence written somewhere else.** Artifacts left in a rehearsal or repair directory, so
  the run-owned ledger and manifest the evidence gate reads are missing. The scored run is the
  one that writes evidence; a dry run is `--out-dir` scratch and counts for nothing.
- **A scenario that confounds its own assertion.** Steps that self-heal, retry destructively,
  or fall back to a second path make the final assertion inconclusive — it cannot say which
  path produced the result. One scenario, one causal story.

## Classify what survives

Return `stands` only when no concrete refutation survives. A refutation must be classified:

- `plan-defect`: the frozen plan did not actually test a required objective;
- `evidence-defect`: the claimed proof is missing, stale, incoherent, or does not support its
  coverage claim; or
- `product-contradiction`: current evidence directly demonstrates behavior contrary to the
  claimed pass.

The auditor never repairs or extends QA. It may not upgrade any result or turn a plan/evidence
defect into a product claim.

## Record the audit in `qa.md`

`<spec_dir>/qa.md` is a short current-state document — `## Verdict`, `## Assessment`,
`## Independent Audit`, `## History` — and `qa-report.md` beside it carries the evidence.
**Replace** the `## Independent Audit` section in place (one audit: this one), naming the
criteria, obligations and evidence you sampled, the report warnings you weighed, and any
concrete refutation. Do not append a second audit below an old one, and do not touch the
other sections except to add one line to `## History` for this run when the section exists.

A green run often reaches you before anyone has written `qa.md` at all. When it is absent,
create it through `ostler` — `timeout 30 ostler create spec <story-name> qa.md`, where
`<story-name>` is the folder name of `<spec_dir>` — which stamps the `type: spec.qa`
frontmatter that makes it an OKF Concept. Write below the `---` block and leave it intact:
`# QA — <story-name>`, a `## Verdict` of one or two lines (runner status, run id, date,
pointer to `qa-report.md`), `## Assessment` reading "_confirmed by the runner; see
qa-report.md_", your `## Independent Audit`, and an empty `## History`.

## Commit Identity

Every commit subject ends with `[{{ workhorse_var('story_id') }}]`, after its description.
Every commit also carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_id') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Output

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
