# QA in thirty minutes per story — or a checkpointed block, never a corpse

The QA lane is where the coder workflow's money and wall clock go to die. Across the six
QA-lane runs since the reviewer's deletion (`qafix4`–`qafix9`, `pe90f9b97`), the `qa`
sub-flow consumed 2,521 minutes over 26 story visits — **~97 minutes mean per story, with
a tail past ten hours**. `groom loops --workflow coder` puts the bulk of the fleet's lap
excess in this lane (the corpus-wide table mixes in pre-deletion runs; the post-deletion
per-node numbers are below), and the exit rates say why: historically `plan-qa` exited at
27% and `repair-qa-plan` at 18% (mean 5.4 laps, max 33) — and post-deletion, plan + repair
still average ~4.5 authoring/repair turns per story.

The target is **≤30 minutes of QA per story** in the common case. One approach is already
tried, failed, and its lesson recorded in the tree: `014ebcb` made `plan_lane_budget_s` /
`qa_lane_budget_s` terminal, and two live stories that had reached a green 41/41 runner
were stamped `[QA FAILED — needs manual review]` because the clock expired before the
post-run gates signed off — the `QaLoop` docstring now carries the postmortem, and the
budgets survive only as **advisory** logged signals. A wall clock cannot tell a loop that
is going nowhere from one that is three turns from green. So the 30-minute figure in this
plan is **never enforced by killing anything**: it is reached by making the work smaller
(§2–§4), the laps cheaper and fewer (§5), and the tooling faster (§6) — and where a story
still cannot finish inside a sane envelope, the lane parks on `Await`, checkpointed and
resumable, exactly as the no-give-up rule already demands. The advisory budgets stay:
"ran 3× its budget" is the honest operator signal; it is just not a verdict.

Written 2026-08-20 after a `/stablemate-brainstorm` grounded in groom telemetry; nothing
below is implemented. Companion plans, not duplicated here:

- [optimize.md](optimize.md) owns the dev-lane diet and the prompt-ownership argument.
  Everything it says about prompts briefing every stack ever deployed applies to
  `apply-qa-fixes` and `plan-qa` too, and lands via that plan, not this one.
- [blocked-handoff-and-session-memory.md](blocked-handoff-and-session-memory.md) owns the
  dropped-verdict defect and lap amnesia. The qafix9 pathology (12h29m of QA against a
  story that was never implemented) was *caused* upstream by a discarded `blocked`
  verdict; no QA-lane optimization fixes that, and that plan is a prerequisite for the
  numbers here to hold in adversarial cases.
- [optimize-baseline.md](optimize-baseline.md) sets the measurement discipline this plan
  inherits: no step below claims a number without a timed run against the baseline in §1.

## Where a story's ~97 minutes actually go

Post-deletion runs only (`qafix4`–`qafix9`, `pe90f9b97` — the tree as it is today):

| Step | share of lane wall clock | telemetry |
| --- | --- | --- |
| `apply-qa-fixes` | **~50%** (1,256 min) | 66 visits, mean 19 min, max **8.8 h** |
| `repair-qa-plan` | 13% (327 min) | 59 visits; historically mean 5.4 laps, max 33 |
| `plan-qa` | 10% (250 min) | 58 visits; historically 27% exit |
| `qa-story` | 8% (204 min) | 92 visits |
| `build_okf_context` | 2.4% (61 min) | **102 visits × ~28 s** — rebuilt on every rejoin |
| `run_qa_plan` | 1.6% (41 min) | 60 s avg |
| `audit-qa` + `validate_qa_plan` + `lint` + rest | ~10% | audit loose (1.7 laps), validate 21 s, lint ~1 s — the machine gates are already cheap |

Two structural facts behind the table:

1. **The fix turn is one open-ended blob.** `apply-qa-fixes` is handed every failing
   scenario at once with no per-item bound, so its distribution has a 20-minute mean and
   an 8.8-hour tail. Its 35% exit rate then feeds `qa-story` again, which re-runs the
   whole suite to find out what one fix did.
2. **Ostler pays cold-start per visit and per agent tool call.** The `Ostler` facade
   caches its repo snapshot *per instance* (`ostler/ostler/api.py`), but every node visit
   constructs a fresh instance, so the 28 s snapshot build ran 102 times. Agents inside
   turns shell out to the `ostler` CLI, which pays a full interpreter + snapshot start
   every call — time that hides inside the agent-turn spans above.

## 1. Baseline first (prerequisite, ~one command)

The harness already exists: `benchmarks/replay.py` freezes a finished benchmark app,
rewinds one story's QA flow, and re-runs `workhorse-coder run qa` standalone, with
`--label` naming the configuration so `report` compares exit rates per node across labels
(it reads `groom.store.loop_convergence`, the same function behind `groom loops`). The
scored mode (`--fixture … score`) supplies the guard the lap count alone cannot: a flow
that approves everything converges in one lap, so detection against `defects.yml` is what
keeps a "faster" QA lane honest.

What history cannot be is the *before* arm. The corpus straddles the reviewer deletion
(`b619a7e`) and the terminal→advisory budget change, so "after vs. history" attributes
tree drift to the change under test; the story mix differs per run; and the existing
`replay-*-qa-*` labels predate `b619a7e`. So the baseline is one labeled run on the
unmodified branch point, launched first and left to run in the background:

```bash
benchmarks/replay.py capture                    # refresh the bundle if source moved
benchmarks/replay.py run --flow qa --story expense-list -n 3 --label before
```

Record the resulting table next to [optimize-baseline.md](optimize-baseline.md)
(`git add -f` past the `docs/plans/*` ignore). Every section below reports a same-story
`--label after-<section>` run against it — the memory rule
`feedback-measure-before-claiming-optimization` made executable. History keeps the job it
is good at: motivating this plan and ranking its levers.

## 2. Break up `apply-qa-fixes` — the 50% lever

Target: fix time ≈ (failures × bounded item cost), never one unbounded turn.

- **One fix item per failing scenario.** The turn is briefed with exactly one scenario's
  failure, its evidence dir (`qa/<id>/`), and the plan's `verify:` for that scenario. It
  dry-runs only that scenario (`ostler qa run … --scenario <id> --out-dir <id>`) before
  returning — the same "a repair unobserved is a hypothesis" rule `repair-qa-plan`
  already enforces. Re-running the full suite happens once, after the worklist drains,
  not per hypothesis.
- **Route by failure class, don't fix in place.** `triage-qa` already classifies. A
  `product`-class failure is dev work: it goes back through the dev flow's fix machinery
  (which has lint, verify, and review gates) instead of being patched by a QA-lane turn
  with none of them. The QA lane keeps only `evidence`- and `environment`-class repairs.
  This is also the correctness fix: five consecutive `apply-qa-fixes` turns in qafix9
  reported `passed` while QA never passed — a fix turn that cannot see the dev gates
  should not be doing dev work.
- **Per-item budget, spent toward `Await`.** Each fix item gets a turn timeout sized to
  its class (minutes, not 45); an item that exhausts it is validated-as-written (the
  existing `AgentTimeout` → validate pattern in `repair_plan`) and, on a second identical
  failure, becomes a block — not another lap. No kill, no give-up: the worklist parks.

Files: `coder/qa/flow.py` (`apply_fixes` state → worklist loop), `coder/qa/nodes/qa.py`
(per-scenario run helper exists), prompts `apply-qa-fixes` → `qa-fix-item`,
`coder/dev/flow.py` (entry point for routed product failures — coordinate with
[optimize.md](optimize.md)'s repair-prompt consolidation rather than adding a fifteenth
repair prompt).

Expected: the 8.8 h tail becomes structurally impossible; mean fix time bounded by
failures × ~4 min. This is the only change that can get the mean under 30 minutes at all.

## 3. Shrink the plan lane's remaining laps — build on what `b619a7e` already did

Most of the classic advice here is already implemented, and this plan must not undo it:
the reviewer is deleted (`b619a7e`, replaced by `ostler qa lint`/`validate`/`evidence-map`
— 78 of its 79 blocking findings were machine-computable), the stack comes up *before*
planning so an authoring turn can dry-run a scenario it just wrote, repairs run at
`power="low"` on a chained session and must prove their fix with a per-scenario dry run,
and the plan-qa prompt deliberately **forbids** the turn from running whole-plan
validation itself (the deterministic node does it in 21 s; an agent re-deriving it is the
expensive version). Do not reopen any of that.

What's left is that plan + repair still spend ~577 min across 26 stories (~22 min/story)
at ~4.5 turns per story. The turns are not failing at *import* (lint/validate are cheap
and mostly pass); they are failing at the runner and coming back as evidence-class
repairs. Two levers:

- **Seed the prompt with the rejection taxonomy.** `groom transcript ls --by-node
  plan-qa` / `repair-qa-plan` across the archive, cluster what actually sends a plan
  back — validator findings are structured, and runner failures are classed by
  `triage-qa`, so the clustering is mostly mechanical. Put the top N into the planner
  prompt as named anti-patterns (the straight-apostrophe-vs-U+2019 fixture mismatch and
  the password-constant drift in the flow's own docstrings are exactly this shape). A
  27% historical exit rate is systematic, not noise (qafix9: seven plans at ~35 KB
  each). One archive-mining session, then a prompt edit — cheapest item in this plan.
- **Make the first authoring turn dry-run its riskiest scenarios.** The machinery exists
  for repair (`verify_qa_dry_run` reads per-scenario evidence) and the stack is already
  up; the *plan* turn currently passes `dry_run=()` because it has no failing set. Give
  it one: the prompt asks the author to execute the 1–2 scenarios most likely to break
  (first browser scenario, first credentialed one) before returning, and `_validated`
  reads that evidence when present. Failures the suite run currently discovers one full
  lap later get caught inside the authoring turn, where the context is hot.

Files: prompts `plan-qa`, `repair-qa-plan`; `coder/qa/flow.py` (`_validated`'s `dry_run`
arm gains a plan-turn caller). Expected: plan-lane turns per story from ~4.5 toward ~2.

## 4. Cap the plan by the obligation packet

`ostler qa context` already computes exactly which obligations this story's diff created
(`qa-okf-context.json`, fail-closed). Make the planner's scenario budget derive from it:
one scenario per obligation plus the story's acceptance criteria, and the reviewer/gate
*rejects over-planning* the way it rejects under-coverage today. Every downstream cost —
validate, dry-run, suite run, fix items, audit — is linear in scenario count, so this is a
multiplier on §2 and §3, not an independent saving. The contractual fail-closed direction
(`covers:` may not narrow) is untouched; this bounds the other side.

Files: prompt `plan-qa`, `coder/qa/nodes/evidence.py` (coverage check gains an upper
bound), possibly `ostler qa validate`.

## 5. Lap discipline — distinct findings only

- **Two identical rejections → block.** `_repeating` exists and resets the session chain;
  it should also *stop the loop*. A lap that fails at exactly what the last lap failed at,
  twice, goes to the operator gate with both laps' evidence attached — `repair-qa-plan`'s
  observed max of 33 laps is 31 laps of the run arguing with itself. The no-cap-on-
  escalations rule makes this safe: the operator can always send it back around.
- **Tiering is already half-done — finish it.** `repair-qa-plan` runs at `power="low"`;
  give `qa-fix-item` (§2) and the post-first-lap validation passes the same treatment,
  and measure whether low-power repairs lower the exit rate before keeping it (§1
  harness).

Files: `coder/qa/flow.py` (`_repeating` call sites gain an `Await` arm through the
existing `MAX_QA_BLOCKS` resolver path — the vocabulary in
`coder/shared/resolution.py`, and mind `check-no-giveup`).

## 6. Make ostler stop paying cold-start — the named pain

Three fixes, smallest first, all in ostler rather than the workflow:

1. **Reuse the packet when the diff hasn't moved.** `build_okf_context` keys a hash of
   its effective inputs (base, head tree-hash, dirty-path digest, excludes) into the
   packet it writes; an identical hash on a later visit reuses the packet. 102 visits
   collapse to roughly one per story plus one per real diff change. Pure workflow-side
   memoization, no ostler change: `coder/shared/okf.py`.
2. **Persist the snapshot across instances.** `Ostler` gains an on-disk snapshot cache
   keyed by `(docs_root, HEAD, dirty digest)` so a fresh instance with an unchanged repo
   loads in ~1 s instead of rebuilding for ~28 s. This also serves every *other* lane
   and the agents' CLI calls: `ostler/ostler/api.py` plus the CLI entry.
3. **Profile before optimizing further.** 28 s for a context map smells like one hot
   loop (whole-tree symbol inventory). `py-spy` one `ostler qa context` run before doing
   anything cleverer than caching — an incremental inventory is a bigger project and may
   be unnecessary once (2) lands.

Expected: ~60+ min of visible deterministic time across the corpus, plus the invisible in-turn CLI
cold-starts, drop to noise. This never gets a story from 97 to 30 alone — which is why
it is §6 and not §2 — but it is the only section that makes *agents'* ostler calls
cheaper, and those sit inside the ~50%.

## The 30-minute story, assembled

| Step | budget | comes from |
| --- | --- | --- |
| context build + validation (deterministic) | ~1 min | §6 |
| plan turn, incl. its own risky-scenario dry runs | ~8 min | §3 |
| suite run | ~2 min | today's `run_qa_plan` avg |
| audit | ~2 min | already loose; unchanged |
| fix items, 2–3 × ~4 min bounded | ~12 min | §2 |
| one repair lap when needed | ~3 min | §3, §5 |
| re-run + slack | ~4 min | |
| **total, common case** | **~30 min** | |

A story that blows this envelope doesn't die and doesn't loop to a cap — it parks on
`Await` with evidence (§2, §5), which costs the operator the same ten minutes it always
would have and costs the run nothing it hadn't already spent.

## Order of work

1. §1 baseline label via `replay.py` — launched first, runs in the background; nothing is claimable without it.
2. §6.1 + §6.2 — mechanical, isolated, immediately measurable, no workflow semantics.
3. §2 — the 50% lever; biggest change, do it while the baseline is fresh.
4. §3 — taxonomy mining plus the authoring-turn dry run.
5. §5 — lap discipline (small diff once §2/§3 reshape the loops it guards).
6. §4 — scenario budget, last, because it touches the contractual coverage gate and
   wants the reshaped lanes settled first.

Each lands as its own commit(s) per the commit procedure, measured against §1 before the
next starts.

## Progress

### 2026-08-20 — QA-lane baseline, label `before`

`replay.py run --flow qa --story expense-list -n 3 --label before`, `opencode` /
`openrouter/openai/gpt-5.6-luna`, fixture `expense-split` @ `c0478a9`. All three trials
exited 0.

```
node                           items turns   exit  mean  max    cost$
plan-qa                             3     3  100%  1.00    1    $0.29
audit-qa                            3     3  100%  1.00    1    $0.12
repair-qa-context                   3     3  100%  1.00    1    $0.12
qa-story                            3     3  100%  1.00    1    $0.10
———————————————————————————————————————————————————————————————————
TOTAL                                                           $0.64   (0 excess turns)
```

Wall clock: ~35 min for three trials, ≈11–12 min per trial (03:16 → 03:51 EDT).

**Read this baseline as a floor, not as a refutation of the plan.** `groom loops` measured
`plan-qa` at an 18% exit rate *across every run on this machine*; here it exits first lap
three times out of three, and `apply-qa-fixes` — §2's 50% lever — never ran at all,
because the frozen tree's QA passes. One story that converges cleanly cannot show a
convergence problem, so this label is only useful as the "did a change make it worse"
control: any after-label that turns one of these 100%s into a loop is a regression, and
§2/§3's real evidence has to come from a story whose QA fails, or from `score` against a
seeded-defect `app:` fixture.

Two fixture defects had to be fixed before a trial could reach an agent turn at all, both
recorded in the commits alongside this note: the `expense-list` pin (`2c2b1b2`) was
reachable from no ref in the source repo, so `git bundle --all` had been silently dropping
it, and the story it pins predates the `## Dependencies` section `prepare_story` now
requires — `expense-list` is re-pinned at `c0478a9`, that commit plus the missing section.
