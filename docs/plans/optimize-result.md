# Result: what one dev-lane story costs after the optimize plan

Steps 7 and 11 of [optimize.md](optimize.md), measured against
[optimize-baseline.md](optimize-baseline.md). Like the baseline, this file is `git add -f`'d
past `.gitignore`'s `docs/plans/*`: a plan is scratch, a measurement a later change must not
silently regress is not.

Measured 2026-08-19/20 on `/tmp/bench-expense-split`, story `expense-list`, same model tier as
the baseline, with `benchmarks/devlane.py`.

```bash
uv run python benchmarks/devlane.py run   --repo <bench-repo> --at <sha> --story expense-list --run-id b1
uv run python benchmarks/devlane.py table --repo <bench-repo> --run-id b1 --story expense-list
uv run python benchmarks/devlane.py laps  --repo <bench-repo> --run-id b1
```

## The success table

| Metric (per single-service story)                   | Baseline | Target | Measured |
| --------------------------------------------------- | -------- | ------ | -------- |
| High-power agent turns on the happy path            | 3 | **2** | **2** ✅ |
| Agent turns on a one-lint-failure path              | 4 | **3** | **3** ✅ |
| Distinct result schemas parsed by `dev`             | 5 | **3** | **4** — see below |
| Lines under `coder/prompts/` naming a stack/tool    | many | **0** | **0** ✅ (`make check-prompt-agnostic`) |
| Wall-clock, median story, happy path                | 22.7 min | ≥30 % lower | **not claimed** — see below |
| Stories ending `WorkflowFailed` on a budget         | 0 | 0 | **0** ✅ |
| Fix-lap success rate, per source                    | no data | not lower | measurable; `goal` 4/5, `tdd` 1/2 |

## Every run at this tree

| run | turns | high-power happy path | repairs | wall clock | cost |
| --- | ----: | --------------------: | ------: | ---------: | ---: |
| baseline | 3 | 3 | 0 | 22.7 min | $6.22 |
| `a14` | 2 | 2 | 0 | 11.7 min | $4.64 |
| `a15` | 3 | 2 | 0 (implement re-entered) | 14.5 min | $5.51 |
| `b1` | 3 | 2 | 1 | 21.5 min | $8.86 |
| `b2` | 2 | 2 | 0 | 16.5 min | $5.61 |
| `b3` | 2 | 2 | 0 | 11.8 min | $4.74 |

The happy path is `plan-story` + `implement-plan`. `check-code-reuse` is gone, and a repair is
one `dev-fix` turn against a `FailureReport` rather than a source-specific node — which is
what turns the "one-lint-failure path" row from four turns into three.

## The three rows that are not a plain ✅

**Schemas: four, not three.** `PlanResult`, `ImplResult`, `FixResult` — the three the row asks
for — plus `OperatorResolution`. The fourth is the operator gate's, shared by every lane;
folding it into the lane's three would mean the gate had stopped being a cross-lane concern.
Counted rather than argued down.

**Wall clock is not claimed.** 11.8–21.5 min across five runs of the same story, against a
22.7 min baseline of n=1. The spread between two runs of the same story is larger than the
difference from the baseline, and `implement-plan` alone ranged 373–891 s. Step 11 forbids
Plan B from claiming this row, and the numbers agree. The baseline's own diagnosis stands:
both remaining turns spend their time reading real code, and nothing here changed that.

**`lint` and `test` produce no fix laps — by construction, not by luck.** Two runs seeded a
deliberate lint-red and test-red defect (`b2` in the package the story touches, `b3` in one it
never touches). Both times the implement turn found and repaired them before any gate ran:
`b3`'s turn ran `git show` on the seed commit and `go test ./...` unprompted, because the
envelope's exit conditions tell it what done means and `agents.yml` tells it how to check.
Anything the `lint` or `test` gate can see, the turn can now see, because the turn runs the
same command. The laps that remain are at the two sources the turn *cannot* self-check —
`goal` (did the promise hold) and `tdd` (was the failing test first).

The row cannot have regressed against the baseline, which recorded no laps at all and called
itself unfalsifiable until some existed. It is falsifiable now, per source, on any future run.
