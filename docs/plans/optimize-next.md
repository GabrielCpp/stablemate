# optimize-next: pay the owed rows, then cut the tail

Successor to [optimize.md](optimize.md) and the overnight ledger, written the morning after
(2026-08-20, tree at `fa840ac`). The previous program ended with real numbers and two rows it
refused to claim; this one exists to make those rows claimable and then to move the number
that is still the biggest: the dev lane's slow tail.

The rules carry over unchanged: **no optimisation is claimed without a timed run**
(memory: `feedback-measure-before-claiming-optimization`), medians over every run rather
than the best one, and a give-up is never an exit — only `Await` is.

## Where the numbers stand, and what the data ranks first

From `optimize.md`'s two filled tables plus the per-node breakdown of runs
`a12`/`a14`/`b1`/`c1`/`d1` (re-derivable with `devlane.py table --run-id <id>`):

- **Dev lane: median 14.5 min (n=9) against the 22.7 min baseline — 36 % — on a spread of
  11.0–23.2 min.** The spread is not noise evenly distributed: `plan-story` is stable
  (~330 ± 40 s across runs) while **`implement-plan` spans 276 → 891 s (3.2×)**, and its
  tool calls (23 → 75) and context volume (1.2 M → 7.2 M cached tokens) track the wall
  clock exactly. The tail *is* the implementer's turn length. It already resumes the
  planner's session (`dev/flow.py`, `session=self._story_chain()`), so "stop re-reading"
  is not the remaining lever — what the extra ~50 tool calls in a slow run actually do is
  unknown, and finding out is step T1.
- **`dev-fix` records `high` power on every lap** in every table, although
  `dev/flow.py:750` reads `power="high" if stalled or fix_lap >= 2 else "low"`. Either
  the ladder misfires or the telemetry reports the wrong thing; both readings matter
  (one costs money and seconds, the other falsifies every power column we quote).
- **The fix-lap row is owed for a structural reason**: the bench seeds lint-red/test-red
  in `member`, a package the measured story never touches, so A-side runs produced only
  `goal` laps and B-side only `test` laps — no shared source, no comparison. The "seeded
  to fail once per source" story was named twice and never built.
- **QA lane: the floor is measured (~11 min/trial, no regression), the envelope is not.**
  Nothing yet scores what QA does when the code is genuinely defective — the seeded-defect
  fixtures (`benchmarks/apps/*/defects.yml`) exist for exactly this and have never been
  scored against.
- **ostler cold start**: the snapshot cache took repeat loads to 0.023 s, but the cold
  path is still ~60 s on the 550-doc book, and the Q4 profile already named the culprit:
  `_load_features` re-tokenizes markdown 9,325 times for 844 docs (driven by `refs`),
  57.7 s of the 60.3 s total.

## Phase M — make the owed rows measurable

Measurement first, because every later step's claim depends on it.

- [ ] **M1 — distribution, not anecdotes.** Give `benchmarks/devlane.py` a batch mode
  (`run --count k`, sequential is fine) and teach `table` to report a distribution over a
  set of run-ids: median, IQR, p90, per-node medians. Then **pre-register the claim rule
  in this file**: a change may claim a wall-clock effect only if the median over ≥ 5
  fresh runs moves by more than half the pooled IQR. The 11–23 min spread on an identical
  tree is why n=2 could claim nothing last time; this makes "how many runs is enough" a
  written rule instead of a judgment call made after seeing the data.
- [ ] **M2 — the per-source seeded story.** Cut bench commits on
  `/tmp/bench-expense-split` seeding exactly one failure per `FailureReport.source`
  (`lint`, `test`, `goal`, `tdd`, `regression`) **in the story's own path**, not in
  `member` where the current seeds sit untouched. Done when one batch run fires every
  source exactly once and `devlane.py table` shows a per-source lap count — that fills
  the fix-lap row on any tree from now on, which no amount of re-running could do before.
- [ ] **M3 — the QA envelope score.** A harness (sibling of `replay.py`) that runs the QA
  lane against the seeded defects in `benchmarks/apps/*/defects.yml` and scores:
  defects caught / defects passed through / fix laps spent / minutes. Record the baseline
  score for the current tree. This is the measurement the Q phase explicitly deferred;
  until it exists, "QA works" means only "QA is fast when nothing is wrong."

## Phase T — the implement-plan tail

The data ranks this first among wall-clock levers: the median is fine, the tail is not,
and the tail is one node.

- [ ] **T1 — diagnose before touching.** Pull the transcripts of the slow implementers
  (`groom transcript ls --run b1 --node implement-plan`, likewise `c1`) against a fast one
  (`a12`, 23 tool calls) and write a taxonomy of what the extra ~50 tool calls do —
  exploration, repeated gate runs inside the turn, retry-shaped flailing, or legitimate
  size differences. Deliverable is the written taxonomy in this file, **no fix yet**. The
  fix chosen without this is a guess wearing a number.
- [ ] **T2 — act on T1's top class, claim via M1.** Candidate mechanisms, to be chosen by
  the taxonomy rather than preference: an exit rule against in-turn gate re-runs (the
  deterministic gate re-runs anyway, so a turn that runs the suite three times pays twice
  for nothing); a tool-call soft budget surfaced in the envelope; splitting oversized
  implementation turns along `implementation_order`. Whatever lands claims p90/median
  movement only through an M1 batch, before/after.
- [ ] **T3 — the dev-fix power ladder.** Establish whether lap 1 really runs high
  (ladder misfire — e.g. `stalled` true on a first lap) or runs low and is *reported*
  high (devlane/groom reading declared rather than actual power). Fix whichever it is,
  with a test. If the ladder was misfiring, an M1 batch on the seeded-lap story (M2)
  records the seconds a low-power first lap buys; if it was telemetry, every power
  column previously quoted gets a correction note here.

## Phase Q2 — QA's remaining seconds, then its envelope

- [ ] **Q2-1 — ostler cold start, the named 57 s.** Memoize `_load_features`' per-file
  markdown tokenization (keyed the way the snapshot cache keys its dependencies), so 844
  docs cost 844 tokenizations, not 9,325. Target: cold `ostler qa context` ≤ 10 s on the
  550-doc book, measured by the same profile that found the number.
- [ ] **Q2-2 — tune the fix machinery against M3's score.** With the envelope baseline
  recorded, the QA lane's budgets stop being folklore: measure whether
  `MAX_FIX_ITEM_REWORKS = 2` and the product-class routing to dev actually maximize
  defects-fixed-per-minute on the fixture set, and adjust only what the score moves.
  Done when the score is not lower than baseline and at least one budget decision cites it.

## Phase H — flagged follow-ups, so they stop being follow-ups

- [ ] **H1 — `_align_pwd` for `cwd is None`.** Generalize
  `workhorse/runner/process.py::_align_pwd` to also align `$PWD` when a node declares no
  `cwd` — the twin of the replay-sandbox leak (`f76c5ba`), where an inherited `$PWD`
  named a directory the child had left and the agent CLI believed it. With a test.
- [ ] **H2 — decide smoke-as-a-gate.** It was scoped out of D3 deliberately. Decide it
  now, in writing, either way — a sentence here saying "no, because…" is a decision; a
  gate that drifts in through a later prompt edit is not.

## Success table

| Metric | Baseline (this morning) | Target | Claim rule |
| --- | --- | --- | --- |
| Dev median wall-clock, happy story | 14.5 min (n=9) | ≤ 12 min | M1 batch, pre-registered rule |
| Dev p90 wall-clock | ~22 min (b1/c1-shaped tails) | ≤ 17 min | M1 batch |
| Fix-lap success rate, per source | no shared source ever measured | a rate for all five sources | M2 story, both before/after any T2 change |
| `dev-fix` lap-1 power | `high` (observed, contradicting flow.py:750) | `low`, or the column corrected | T3, with a test |
| QA envelope score | unmeasured | baseline recorded, then not lower | M3 then Q2-2 |
| ostler cold `qa context`, 550-doc book | ~60 s (57.7 s in `_load_features`) | ≤ 10 s | same profile, before/after |
| Replay/workhorse `$PWD` alignment | replay fixed, workhorse conditional | unconditional, tested | H1 |

Order: M1 → M2/M3 in parallel → T1 → T3 → T2 → Q2-1 → Q2-2 → H1/H2. M before T is
load-bearing: T2 without M1 is how a cherry-picked run gets claimed, which is the exact
failure the last program spent two rework items refusing.
