## The auditor's brief

Hand this section to the auditor. It starts fresh, on the strongest model, and it sees the
story, the plan and the evidence of the scored run, never your reasoning or your
assessment. It tries to refute the run's verdict. It executes nothing, edits no plan and no
evidence, and writes only the `## Independent Audit` section of `qa.md`.

### What it reads

- `qa-report.md` first: each criterion and obligation with its verdict, the step each
  covering assertion ran in, its observed and expected values, the screenshots behind it, and
  a `## Warnings` list. The warnings and every `UNPROVEN` row are where a refutation starts.
  Its run marker (`<!-- run: ... -->`) must name the run in `qa-evidence.json`.
- `qa_plan.py`, `qa/qa-run.ndjson`, `qa/run-manifest.json` and the story's acceptance
  criteria.

### Coverage is computed

Run the map from the spec dir instead of joining the files by hand:

```bash
ostler qa evidence-map
ostler qa evidence-map --status uncovered
```

Each row carries `status`, `why`, `checksDeclared`, `checksObserved`, `checksMissing`,
`claimedBy`, the assertion counts, `logRefs` and the `evidence` files. Route on `status`:

- **`covered`**: passing assertions back it and every declared check ran. Nothing to file.
- **`claimed-but-unasserted`**: a scenario claimed it and no passing assertion backs it, or a
  declared check never ran. An evidence defect.
- **`uncovered`**: nothing claimed it. A plan defect.
- **`contradicted`**: the ledger and `qa-evidence.json` disagree, or a bound assertion failed
  under a pass. Always a refutation: quote both sides from `why` and `failingLogRefs`.
- **`insensitive`**: every declared check passed, and no observation could have failed them.
  An evidence defect in the declaration, never a product refutation on this ground alone.
- **`unproven`**: the scenario that would have observed it did not finish. An evidence
  defect whose repair is in the plan. Never file it against the product.

A row with no `checksDeclared` is a book gap. Say so in `notes`, and do not refute on it alone.

With the map read, sample the riskiest evidence for what it cannot compute: persistence and
reload, event consumers, concurrency, idempotency, state isolation, journey completion,
visual state, recording continuity and error handling. Judge clause partiality on the
acceptance criteria: an AC that promises three things and proves one is a plan defect the map
calls `covered`. A required flow's evidence begins at its documented start and reaches its
documented end.

### What the page asked the network for

Open `qa/traces/<scenario>-diagnostics.json` for every browser scenario. Two findings are
`contradicted`, never a judgement call: a non-empty `pageErrors`, and any response at 500 or
above. Refute as a product contradiction when a 4xx answers a request no step provoked,
sharpest when it repeats per row or per poll, quoting the `url`, the `status` and the count.
Refute too when a `console` entry names a product failure: an unhandled rejection, an error
boundary, a hydration mismatch. Do not refute on console noise alone, on a
`failedRequests` entry with no status, or on a 4xx the scenario's own steps asked for. Check
an endpoint's `errors:` bullets before calling a documented error a defect.

### The layout

Read the `<name>.layout.json` beside every screenshot. On a viewport at least 900px wide,
refute as a product contradiction when the primary content region has `viewportWidthShare`
below 0.4 with no sibling filling the rest, when its `startsRightOf` is above 0.5 with
nothing in the left half, or when `flags` is non-empty (`horizontal-overflow`,
`region-starts-off-screen`). Quote the measured numbers. A `device-layout/1` digest always has
empty `flags`, so judge a device screen from its vet report. Read `<name>.vet.json` first
where it exists: a `misplaced` or `missing` verdict is the book's own, so quote it. A browser
scenario with no screenshot is a plan defect.

### Green scenarios that prove nothing

- `covers=` names an obligation no step reaches.
- One branch of a conjunction asserted, or one arm of a disjunction.
- An assertion that would pass under the failure it claims to catch.
- Evidence that exercises a neighbouring method, route or component.
- Proof by absence: no error banner is not a rendered result.
- An oracle over a field the runner never writes.
- An error path no scenario triggers.
- Three known objects checked where the claim is about the whole collection.
- A terminal proof the runner cannot make: "the chart renders", a colour judged by eye.
- A fixture that passes once and fails on the rerun.
- Timing asserted without a wait on an observable condition.
- Evidence written to a scratch directory instead of the scored ledger.
- Steps that self-heal or fall back, so the final assertion cannot say which path produced it.

### The verdict

It returns `stands` only when no concrete refutation survives. Each refutation is one of:

- **plan defect**: the plan did not test a required objective;
- **evidence defect**: the claimed proof is missing, stale, incoherent or does not support
  its claim;
- **product contradiction**: the evidence shows behaviour contrary to the pass.

It never upgrades a result, and never turns a plan or evidence defect into a product claim.
It replaces the `## Independent Audit` section of `qa.md` in place, naming what it sampled,
the warnings it weighed and each refutation. It adds one line to `## History` when that
section exists, and touches nothing else.
