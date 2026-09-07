# TRACEBUS - progress log

## Active direction - Decode-Time Coverage and Selection (2026-09-05)

**Status:** ACTIVE
**Supersedes:** Verified-Success Self-Distillation (closed 2026-09-04 on a
faithful Phase-A refutation, lead-confirmed 2026-09-05)
**Latest gate:** G1 coverage ceiling screen (first attempt KILLED 2026-09-07;
kill withdrawn as a harness artifact the same day — REOPENED)
**Next gate:** G1 coverage ceiling screen (reopened, apparatus-only re-score)

The active ladder is intentionally first so gate selection cannot mistake a
superseded D/T/old-G failure for current work. The unchanged North star, frozen
target, controls, shared metrics, guards, active kill criteria, and dependencies
are authoritative in [`README.md`](README.md). Killed gates of superseded
directions below are permanent evidence and **cannot fire an active-direction
program kill**.

| Gate | Document | Depends on | Status | Result | Date |
|------|----------|------------|--------|--------|------|
| G0 | [`G0_corrective_offpolicy_probe.md`](G0_corrective_offpolicy_probe.md) | A0 housekeeping; frozen corrective/success rows and D1 parents (satisfied) | **PASS** | OFF_POLICY_REFUTED (ratio 0.650–0.712, all ≤1.1); off-policy excluded as explanation for corrective failure | 2026-09-05 |
| G1 | [`G1_coverage_ceiling_screen.md`](G1_coverage_ceiling_screen.md) | A0 housekeeping; frozen D1 parents and scratch artifacts (satisfied); not gated on G0's verdict | **REOPENED** | First attempt killed on `APPARATUS_BLOCKED`; kill withdrawn — the registered `C < 93/147` kill criterion never fired (`C = 101`), both blockers are apparatus | 2026-09-07 |
| G2 | [`G2_selector_train_validation.md`](G2_selector_train_validation.md) | G1 Phase B complete | **NOT STARTED (pending G1)** | | |
| G3 | [`G3_decode_target.md`](G3_decode_target.md) | G2 PASS | **NOT STARTED (pending G2)** | | |
| G4 | [`G4_cli_equivalence.md`](G4_cli_equivalence.md) | G3 PASS only | **NOT STARTED (pending G3)** | | |
| G5 | G5_extra.md | G4 PASS | NOT STARTED |

### 2026-09-05 - Direction defined

The research lead confirmed the success-distill G0 kill was a faithful
refutation (`faithful_refutation`, high confidence): Phase A was a complete,
scored, reproducible measurement — mean delta `2.6/49` vs the `3/49` bar,
sign-flip `p=0.125`, replicate 8 below scratch, retention below `0.95` in 2/5
replicates — and the script's `APPARATUS_BLOCKED` self-report traced to two
scanner self-test defects that could not have changed `eval_resolve` (an
undetected leak could only have inflated treatment, so the FAIL is
conservative). Attribution across the three kills (D3, diverse-replay,
success-distill): **every admissible second-cycle weight update at the
10,696-token/100-update budget on this parent lineage is refuted** —
corrective, mixed, and success-only. The previous README pre-registered the
consequence: the honest next question is the pipeline, not the weights.

The new direction holds the D1 parents frozen and decomposes the `~83/147 →
93/147` gap into two falsifiable claims: **coverage** (G1: does a registered
24-candidate diversified pool contain green patches for `>= 96/147`
task-instances? Full-pool strict verification is the ceiling; `< 93/147`
kills the direction before any selector exists) and **selection** (G2/G3: can
a deterministic outcome-blind rule, fit on TRAIN pools only and frozen by
hash, retrieve `>= 93/147` within the unchanged top-3 strict-verify budget,
beating generation-order and random selection in every seed?). The corrective
off-policy probe carries over as the active G0 per the lead's directive — the
closing mechanism report of the killed directions, binding on any future
corrective reintroduction, unable to kill or rescue this direction. Guard
housekeeping (A0: split the self-matching banned-pattern literal; align
canary seeder keys with `_leak_paths`) is a registered apparatus precondition
before any gate reuses the battery. Negative finding recorded in
[`findings/G0_success_distill_fail.md`](findings/G0_success_distill_fail.md).

### 2026-09-05 - G0 corrective off-policy probe: PASS

Measurement completed faithfully: 189/189 planned NLL evaluations of frozen
corrective and success rows under the D1 parent checkpoints (seeds {0,1,2}).
Cross-process determinism verified (rerun identical, max Δ 0.0). All apparatus
guards passed (banned-pattern, canary, leak-scan, zero-weight sharpness).

**Result slot:** Classification recorded as `OFF_POLICY_REFUTED` —
per-seed median NLL ratios (corrective / success) all ≤ 1.1: seed 0 ratio 0.6504,
seed 1 ratio 0.7103, seed 2 ratio 0.7118. Corrective targets are CLOSER to the
parent policy (lower NLL), not further from it.

**Interpretation:** Off-policy-ness is excluded as the explanation for corrective
transfer failure in the diverse-replay and success-distill directions. Since the
success-distill FAIL (Phase A, mean 2.6/49 vs 3/49 bar, sign-flip p=0.125) used
on-policy success targets and also failed, the parent lineage or interference
accounts are the next mechanistic candidates. This gate is a binding constraint
on any future corrective reintroduction: naive label-search corrective targets
are ruled out; any reintroduction must include on-policy-ization or stratify by
measured per-row NLL.

**Next gate: G1** — coverage ceiling screen (frozen D1 parents, coverage vs selection
decomposition). G0's verdict does not gate G1.

### 2026-09-07 - G1 first attempt: KILLED (preserved record)

Preserved as the record of the first attempt; superseded by the reopening below,
never deleted. G1 Phase A was killed on the ground that the completed run
self-reported `verdict: APPARATUS_BLOCKED` on two blocking conditions, and that
the gate's single permitted apparatus repair had already been spent on the
`provenance_sha256` re-hash.

**Failure mode (as killed):** apparatus, not capability. `exp/g1_report.json`
records `apparatus_blocked: true`, `verdict_reason: NO_DEFECT_GRID_PROPERTY`,
`flags.ordering_ok: false` and `flags.oracle_route_flag: true`, with
`candidate_uniqueness.pooled_mean = 4.53` against the registered `>= 8/24`
precondition. **Causes tried:** one apparatus repair (the `provenance_sha256`
re-hash) and the registered five-probe uniqueness trace, which returned
`NO_DEFECT_GRID_PROPERTY` / `collapse_locus: model`. **Causes remaining at kill
time:** the mtime-only ordering guard itself, and the question of whether a
one-sided validity precondition can block a measurement that cleared its bar —
both unexamined when the kill fired.

**Recorded at kill time, unchanged:** `C = 101` (coverage 34/31/36),
`sanity_pass` true in all three seeds, reproducibility 648/648 bitwise,
banned-pattern/leak/zero-weight guards clean, `PRECONDITION_TENSION: true`.

### 2026-09-07 - Reopening

The research lead withdrew the G1 kill: `harness_artifact`,
`kill_was_correct: false`, confidence high. **The registered kill criterion never
fired.** G1 registers exactly one capability-fatal outcome — `FAIL` if
`C < 93/147` — and the run measured `C = 34 + 31 + 36 = 101`, at or above the
`PASS` level of `96/147`. Per-seed sanity holds (`coverage_model` 29/26/31 against
frozen scratch 20/23/22 less the 2-task tolerance), the registered re-decode is
bitwise identical (648/648 slots, zero mismatches), and the banned-pattern, leak,
gold-reachability and zero-weight guards are clean.

Both blocking failures are apparatus. **(1)** `ordering_ok = false` is a proven
harness bug: `run_pipeline` calls `freeze_pools` unconditionally on every
invocation (`g1_coverage_ceiling_screen.py:1656`) and `freeze_pools` always
rewrites the freeze file, so the 2026-09-07 scoring resume bumped the freeze mtime
past the 2026-09-06 verdicts and tripped the mtime-only guard at line 1398.
Content-level re-derivation shows the freeze is faithful — candidate mtimes
predate all verdicts, the internal sha256 recomputes, the "refusing to change
frozen pool" guard would have raised on any content change, and the 666 physical
verdict rows map 1:1 onto the freeze's unique `(seed, patch-hash)` set with zero
missing and zero extra. The same bug fully explains `oracle_route_flag`, which is
`gold_reachable or not ordering_ok or not freeze_hash_ok` (line 1400) and is true
solely through `not ordering_ok`. **(2)** `candidate_uniqueness = 4.53 < 8` is
genuine, and the registered five-probe trace correctly localizes it to model
sharpness (top-1 prob 0.989-0.997, entropy ~0.02 even at temperature 1.2; dedup
keying exact, decode seeds distinct, uniqueness monotone in temperature) with no

# Superseded direction 3 - Verified-Success Self-Distillation (closed 2026-09-04)

Everything in this section is permanent prior evidence, not the active ladder.
Its FAIL cannot re-trip a program kill for the active direction.

| Gate | Document | Depends on | Status | Result | Date |
|------|----------|------------|--------|--------|------|
| G0 | [`G0_success_distill_screen.md`](G0_success_distill_screen.md) | Frozen corrected-rerun artifacts (satisfied) | **KILLED (first attempt, superseded)** | Killed after 3 engineering repairs failed to reach a measurement; no hypothesis was ever scored | 2026-09-04 |
| G0 | [`G0_success_distill_screen.md`](G0_success_distill_screen.md) | Frozen corrected-rerun artifacts (satisfied) | **FAIL** | Mean eval gain 2.6/49 vs 3/49 bar; sign-flip test p=0.125; retention below 0.95 on seeds 7,8 | 2026-09-04 |
| G1 | [`G1_corrective_offpolicy_probe.md`](G1_corrective_offpolicy_probe.md) | G0 complete (PASS or FAIL) | **RENUMBERED** | Carried into the active ladder verbatim as [`G0_corrective_offpolicy_probe.md`](G0_corrective_offpolicy_probe.md) | 2026-09-05 |
| G2 | [`G2_success_distill_target.md`](G2_success_distill_target.md) | G0 PASS and G1 complete | **NOT RUN (G0 failed - direction closed)** | | |
| G3 | [`G3_cli_equivalence.md`](G3_cli_equivalence.md) | G2 PASS only | **NOT RUN (G0 failed - direction closed)** | | |


### 2026-09-04 - G0 first attempt: KILLED (preserved record)

Preserved verbatim in substance as the record of the first attempt; superseded by
the reopening below, never deleted. G0 was killed on the ground that **three
engineering repairs did not get the gate to a measurement**. No science was
scored: no `report.json`, no verdict, no sign-flip test, no Phase B control
training, and the gate doc's Result section empty.

**Failure mode (as killed):** apparatus, not capability. Both submissions died in
`build_provenance` with `RuntimeError: prospective provenance drift` before any
measurement — the full run (`jobs/G0`, `--seeds 5,6,7,8,9`, exit 1 in 204 s) and
the `n=1` rehearsal (`jobs/G0-dry`, `--seeds 5 --rehearsal`, exit 1 in 101 s).
**Causes tried:** three apparatus repairs against the provenance/freeze path,
including adding the self-only source-drift exemption. **Causes remaining:** the
freeze/argv coupling itself, unexamined at kill time.

### 2026-09-04 - Reopening

The research lead withdrew the G0 kill: `harness_artifact`, `kill_was_correct:

# Previous direction (superseded)

Everything below this heading is permanent prior evidence. It is not the active
gate ladder. In particular, D3's killed memorization result informs the active
direction's design but cannot itself fire an active-ladder program kill.

## Previous status table

| Track/gate | Final status | Preserved result or failure |
|------------|--------------|-----------------------------|
| Track A G0 | PASS | Deterministic TL0 substrate and ambiguity calibration |
| Track A G1 | PASS | Factored mesh execution and cleanup were load-bearing |
| Track A G2 | PASS | Sparse-trace inversion held verification cost nearly flat |
| Track A G3a | PASS | Held-out statement composition transferred |
| Track A G3b | FAIL | Sparse confirmatory self-training missed capability bars; cold start was load-bearing |
| Track A G3b-r | FAIL as registered | Corrective-label volume, not accepted rollout volume, governed the generalization transition |
| Track A G4-pre | FAIL with P1 banked | Exact group ops helped execution but did not reallocate residual learning |
| Track A G4 | FAIL | Loop inversion missed; forward execution and branch inversion banked |
| Track A G4b | FAIL | Exact operators did not fix loop inversion; beam coverage/ranking was the bottleneck |
| Track A G5 | NOT BUILT | Conditional gate was never needed |
| Track A G6 | FAIL | Held-in early stopping was blind to grokking; specialization claim remained unscored |
| Track C T0 | PASS | Reproducible baseline measured |
| Track C T1 | PASS | Corrective supervision beat confirmatory supervision |
| Track C T2 | FAIL | Scorer signal existed but candidate diversity capped its load-bearing value |
| Track C T3 | PASS | Exact-op routing worked on its in-grammar suite |
| Track C T4 | FAIL | Scorer and proposer were idle because exact search saturated the circular suite |
| Track D D0 | PASS | HARD-FN anti-circular suite and honest baseline frozen |
| Track D D0-SWE | READY | 269 CPU-feasible genuine bugs; repo-disjoint split frozen |
| Track D D1 | PASS / BANKED | Corrective mean `0.5782`, target gap `-0.0480` |
| Track D D2 | WEAK_PASS | Exact triage kept; scorer ordering and feedback cut |
| Track D D3 | **KILLED** | Corrective and scratch mean EVAL both `0.5633`; TRAIN `0.7457 -> 0.8326`; gap `0.1824 -> 0.2693` |
| Track D D4 | SUPERSEDED / NOT RUN | Replaced by active G2 only if G1 clears the frozen target |


# Full retained historical log

## Program verdict — 2026-08-06: **GOAL_BANKED** (D1 corrective supervision)

The North star is **not** reached: mean strict resolve `0.5782` is `0.0480` below
the frozen target `0.6262` (README → Frozen target). The D1 result is nonetheless
shippable on its own terms and is recorded here as the program's product to date.
**The program stops at this line pending re-authorization** (`ledger.yml` reads
`status: banked`; a new run must pass `--params '{"reauthorize": true}'`).

**The standalone claim.** Gentle LoRA supervision on *strictly verified corrective*
fixes — patches that repair the agent's own failures — improves an unchanged
CPU-only repair pipeline by **+0.1156 absolute resolve** (`0.4626 → 0.5782`, 85/147)
over the identical un-updated model, and beats the matched *confirmatory* control
trained on already-successful trajectories (`0.5034`) in every seed. Measured on the
49-task held-out HARD-FN eval split (`d0-hardfn-1`, hash prefix `8f9093d7d588`),
3 model seeds, with per-seed gains of +9 / +3 / +5 tasks — clearing the registered

### D1 HARD-FN RESULT (2026-07-19): **HARD PASS; SWE READOUT PENDING**

Corrective primary resolved `85/147` on the frozen HARD-FN eval (per-seed 29/28/28).
The SWE readout on the 269 genuine bugs is PENDING.

