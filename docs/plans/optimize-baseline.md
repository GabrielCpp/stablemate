# Baseline: what one dev-lane story costs today

Step 1 of [optimize.md](optimize.md). Every later step reports against this table, and the
rule the memory `feedback-measure-before-claiming-optimization` states — no optimisation is
claimed without a timed run — is what this file exists to make possible.

Measured on 2026-08-19, on `stable-bench` at `cc4ac56` (the tree after step 2's revert), with
the harness `benchmarks/devlane.py`.

This file is `git add -f`'d past `.gitignore`'s `docs/plans/*`, which holds plans as local
scratch. A measurement later steps must report against is not scratch — if it is not in the
tree, step 7's "30 % lower than what?" has no answer a reviewer can check.

## How to reproduce it

The benchmark repo is a checkout the plan names by path; the harness takes it as an argument,
so a different clone measures the same thing by pointing `--repo` elsewhere.

```bash
uv run --package groom python benchmarks/devlane.py run \
    --repo /tmp/bench-expense-split --at 93d8234 --story expense-list --run-id baseline
uv run --package groom python benchmarks/devlane.py table \
    --repo /tmp/bench-expense-split --run-id baseline --story expense-list
```

`93d8234` is on the bench repo's `bench-baseline` branch — the commit immediately before
`expense-list` was first implemented, plus the `## Dependencies` section today's story
contract requires. `run` resets the tree to it, so the measurement starts from a story that
is genuinely unbuilt; `table` reads groom's `spans` afterwards, so it can be re-derived from
a run whose console output nobody kept.

`expense-list` rather than the tempting `expense-delete`: only the former is a registered,
authored story with an epic behind it.

## The run

Run `baseline` — story `expense-list`, from `93d8234`. Single service (`api`, Go), happy path,
lint clean on the first try.

| # | node | power | s | in | cached | out | tools | briefing | share |
| - | ---- | ----- | -: | -: | -----: | --: | ----: | -------: | ----: |
| 1 | `plan-story` | high | 820 | 225,488 | 2,767,951 | 28,670 | 59 | 5,692 | 0.19% |
| 2 | `check-code-reuse` | high | 36 | 48,734 | 165,326 | 1,727 | 2 | 1,131 | 0.53% |
| 3 | `implement-plan` | high | 505 | 98,854 | 3,590,883 | 20,386 | 53 | 4,457 | 0.12% |

- **Turns:** 3 (3 happy path, 0 repair)
- **High-power turns:** 3
- **Wall clock:** 22.7 min across turns
- **Cost:** $6.22
- **Briefing share of everything read:** 0.16% (11,280 of 6,897,236 tokens)
- **Turns per node:** `plan-story`×1, `check-code-reuse`×1, `implement-plan`×1

Whole-run wall clock — `run.json`'s `started_at` to `ended_at` — is **22.72 min**, against
22.7 min of agent turns. The eight deterministic nodes the lane also ran (`prepare_story`,
`stamp_specs`, `validate_plan_context`, `resolve_impl_context`, `branch_code_repos`,
`select_next_layer`, `run_lint`, …) account for roughly one second between them. **There is
no overhead to optimise: the run *is* its agent turns.**

## The rows the success table needs

| Metric (per single-service story)                   | Baseline |
| --------------------------------------------------- | -------- |
| High-power agent turns on the happy path            | **3** |
| Agent turns on a one-lint-failure path              | **4** (structural — this run linted clean) |
| Distinct result schemas parsed by `dev`             | **5** agent results, plus 2 deterministic |
| Lines under `coder/prompts/` naming a stack/tool    | not yet counted — the guard is step 8 |
| Wall-clock, median story, happy path                | **22.7 min** (n=1) |
| Stories ending `WorkflowFailed` on a budget         | **0** |
| Fix-lap success rate                                | **no data** — no lap ran |

The five schemas are `PlanResult`, `ReuseResult`, `ImplResult`, `FixLintResult` and
`OperatorResolution`; `PlanValidation` and `LintOutcome` come off deterministic nodes and are
not what the plan's row counts. The one-lint-failure figure is read off the flow rather than
measured: `lint` dirty routes to `fix_lint` and back, so it is the three turns above plus one.

Two rows are honestly empty. No lap ran, so there is no fix-lap success rate to be "not lower"
than — step 3 must land its own laps to have a comparison, and until it does that row is
unfalsifiable rather than green. And **n=1**: this is one story on one repo, so a re-measure
that lands within a couple of minutes of 22.7 has not demonstrated anything.

## The hypothesis, killed

The plan predicted this and asked step 1 to settle it:

> If the step-1 table shows briefing is under 10 % of turn time, the de-prompting steps still
> happen, but the wall-clock target above is carried by turn-count and the deterministic gates
> alone.

**The briefing is 0.16 % of what the lane read** — 11,280 tokens of prompt against 6.9 M
tokens of context. Even the worst-case turn is 0.53 %, and that is the cheap one. Reported as
a share of tokens rather than of seconds because no backend records time-to-first-token; it is
a proxy, and it is not close enough to its own threshold for the proxy to matter.

So, for the rest of this plan: **prompt-length reduction may not claim a latency number.**
Invariant 1 is pursued because the wrong stack's advice does active harm, and that argument
stands on its own.

## What the table says the target actually costs

The success table asks for a 30 % wall-clock cut, which is **6.8 min** off 22.7. The plan's
main lever for it is removing a high-power turn — and this run says which turn that is worth:

- `plan-story` is **820 s, 60 %** of the run, 59 tool calls.
- `implement-plan` is **505 s, 37 %**, 53 tool calls.
- `check-code-reuse` is **36 s, 2.6 %**, and **two tool calls**.

`check-code-reuse` is cheap here for a structural reason worth writing down: it resumes the
planner's own session (`_story_chain()`), so it opens on a context that has already read the
codebase and answers from it almost without looking. Deleting it is right — it is a schema, a
budget, a rework lap and a prompt for an advisory answer — but **on this story it buys 36
seconds, not a third of the run.** The "3 → 2 high-power turns" row will go green and the
wall-clock row will barely move.

Which leaves the 30 % where the seconds are: both remaining turns spend their time reading
real code (112 of 114 tool calls between them), and the plan's remaining levers against that
are the ones that stop a turn *re-reading* what the workflow already knows — step 4's rendered
plan content instead of "read `plan-context.json`", step 5's declared commands instead of a
turn discovering how to test, step 6's exit conditions instead of a turn re-deriving what done
means. If step 7 misses the target, this paragraph is where the diagnosis starts, and the
honest reading of this table is that **the target is not yet evidently reachable** — turn count
alone does not get there.
