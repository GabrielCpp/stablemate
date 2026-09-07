# TRACEBUS Research Program

## North star

`fix` - a quiet, CPU-only, local coding agent that produces verified green
patches on real bugs with zero regressions, at a resolve rate high enough that a
developer would rather run it than not. Falsifiable end state: the frozen target
below, cleared on the held-out split, under the registered controls, with the
shipped CLI provably identical to the scored artifacts.

### Frozen target

**This target is unchanged. Do not move or recalibrate it.**

| Field | Value |
|-------|-------|
| Metric | Mean strict full-pipeline resolve rate of the unchanged `fix` pipeline, over parent/model seeds `{0,1,2}` (147 task-instances) |
| Dataset / split | HARD-FN `d0-hardfn-1` (content hash prefix `8f9093d7d588`), the 49-task held-out **eval** split |
| Threshold | `>= 0.6262`, equivalently at least `93/147` resolved task-instances |
| Deadline | 2026-10-31; after this date an unmet threshold is banked or recorded negative, never extended |

Secondary readouts are the unfiltered 98-task SWE EVAL resolve, per-repository
P2P regressions, the source-unseen HARD-FN stratum, and median CPU wall time.
They are reported when available and never replace the frozen target.

---

## Core question

The frozen scratch baseline is `~83/147` (per-parent-seed EVAL resolves
`26/29/28` of 49, hash-verified frozen artifacts). Reaching `93/147` requires
ten additional task-instances.

## Gate ladder

| Gate | Question | Depends on | Exact advance condition | Status |
|------|----------|------------|-------------------------|--------|
| [G0](G0_corrective_offpolicy_probe.md) | Why did corrective targets fail to transfer — are they off-distribution for the parent policy? | A0 housekeeping; frozen corrective/success rows and D1 parents (satisfied) | A decisive registered classification (`OFF_POLICY_CONFIRMED` / `REFUTED` / `MIXED`) with valid apparatus; the verdict itself is not gated and cannot kill this direction | NOT STARTED |
| [G1](G1_coverage_ceiling_screen.md) | Do the frozen 24-candidate pools contain green patches for enough EVAL tasks to make `93/147` reachable at all? | A0 housekeeping; frozen D1 parents and scratch artifacts (satisfied); does NOT depend on G0's verdict | Phase A (EVAL ceiling): summed coverage `>= 96/147` is PASS; `93-95/147` is WEAK_PASS (proceed, recorded risk); `< 93/147` kills the direction. Phase B (TRAIN pools) unlocked only by Phase A PASS/WEAK_PASS | REOPENED (first attempt killed 2026-09-07 on `APPARATUS_BLOCKED`; kill withdrawn as a harness artifact — `C = 101`, kill criterion never fired) |
| [G2](G2_selector_train_validation.md) | Does a registered outcome-blind selector retrieve the covered greens on TRAIN within top-3, beating order and chance? | G1 Phase B complete | Per parent seed on TRAIN: `capture_rate(selector) >= 0.85`, `>= capture_rate(first3) + 0.05`, `>= mean capture_rate(random3, 100 draws) + 0.05`; selector frozen by hash; feature wall time `<= 30 s/task` | NOT STARTED |
| [G3](G3_decode_target.md) | Does the frozen pool + frozen selector clear the unchanged `93/147` target on fresh EVAL pools? | G2 PASS | Total selector resolves `>= 93/147` with selector `> first3` and `> random3` in every seed, discordant-pair exact test `p <= 0.05`, zero regressions, median `<= 600 s/task` is PASS; all bars held but total `< 93` is terminal `WEAK_PASS` (banked) | NOT STARTED |
| [G4](G4_cli_equivalence.md) | Is the shipped quiet CLI exactly the system scored in G3? | G3 PASS only | `147/147` candidate/outcome equivalence, target retained, zero regressions, latency and output contract pass | NOT STARTED |

G0 runs first (cheapest; closes the superseded direction's mechanism question
per the lead's directive) but G1 does not wait on its verdict — only on the
shared A0 housekeeping. G3 `WEAK_PASS` is a terminal banked result, not
permission to run G4.

## Program kill criteria

These criteria apply only to the active G0-G4 direction. Prior D3,
diverse-replay, and success-distill results are inputs to the design and cannot
re-trigger a kill merely by remaining in the history.

- G1 Phase A kills the direction if summed EVAL coverage over parent seeds
  `{0,1,2}` is under `93/147`: the frozen weights cannot produce the missing
  green patches under the registered grid, so no selection rule at any budget
  can reach the target. Because every weights-side lever at the frozen budget
  is already refuted, a G1 kill leaves this program without an admissible
  lever; absent an explicit lead re-authorization of a new lever class, the
  program then concludes `negative`.
- G2 kills the direction if no selector from the registered feature class
  clears all three capture bars in every parent seed after the one permitted
  dig. Post-hoc feature additions or refits do not extend the attempt.
- A valid G3 regression, latency, or safety miss fails the direction. G3 below
  `93/147` with all control and safety bars held is `banked`, not extended.
- No decode-pool-size, temperature, top-p, config, or selector-feature sweep is
  admissible in any gate: the grid and feature class are closed by this
  registration. A miss is a miss.
- G0 cannot kill or rescue the capability direction; only an unfixable
  apparatus fault blocks it.
- Any genuine leak, oracle, lookup, repair, quarantine breach (a G1 EVAL
  verdict artifact inside a G2/G3 closure), or full-parent-zero failure kills
  the active direction. A scanner/reporting defect demonstrated before scoring
  is an apparatus block, never a capability result; failed reproducibility,
  count, budget, or freeze checks reject the measurement as
  `APPARATUS_BLOCKED`. One pre-score apparatus repair per gate may restore the
  registered measurement without changing its intervention or bars.
- If G4 cannot establish exact CLI identity after one apparatus-only repair,
  the product claim is negative.
- If the frozen target is unmet on 2026-10-31, the program ends `banked` or
  `negative`; the deadline and target do not move.
