# Make the coder workflow carry only what a workflow needs

The coder lane is slow for a reason that is not "the model is slow". A single-service story
runs through `plan-story` (498 lines), `check-code-reuse` (a second high-power turn),
`validate_paths`, `implement-plan` (217 lines), `lint`, `fix-lint` — three high-power agent
turns at minimum, each briefed from scratch, each briefed with *every* stack the coder has
ever been deployed against. Across `coder/prompts/` that is ~4,900 lines, of which ~1,900 are
fourteen repair prompts (`fix-lint`, `fix-ci`, `fix-verify`, `fix-regression`, `apply-review`,
`apply-qa-fixes`, `qa-fix-item`, `repair-qa-plan`, …) that differ in almost nothing except
which failure they paste in. Each has its own result schema, its own session chain and its own
`max_*_reworks` budget.

Most of that text is scar tissue: each incident became a paragraph. `qa-stack.yml` health-probe
rules, smoke-run evidence, fixture seeding, backlog filing, codegen, the tool list "curl /
Playwright / Maestro / `pulumi preview`", and Go defaults (`"Go API"`, `appctl`, `cmd/alert`,
`pkg/db`) sit in a prompt that also runs against Flutter, Svelte, Python CLIs and Pulumi. The
workflow is the wrong owner for every one of those paragraphs, and it shows: a planner turn on
the expense benchmark took ~8.6 minutes mostly rediscovering what the target repo already knows.

The working-tree diff on `stable-bench` made this worse in the direction it was trying to fix.
It did remove one agent turn (the reuse check became a deterministic pointer check — the right
instinct) and paid for it with two more mandatory plan sections, a new per-layer `verify` gate
with two agent laps, a `rework_pointers` refine lap at high power, fresh sessions per item
(so the implementer re-reads what the planner read), and repo facts — `verify_command`, TDD
test-setup, where utils live — put in the *planner's* head instead of the repo's. This plan
discards it except for two ideas, relocated: the repo-owned verify command (→ `agents.yml
services`) and TDD (→ a repo-declared gate, below).

Written on 2026-08-19 after a `/stablemate-brainstorm`, revised the same day after a review
of its own risks; nothing below is implemented.

## What "success" means here, in numbers

The plan is judged against the baseline from step 1, on `/tmp/bench-expense-split`, same
model tier, same stories. It succeeds when **all** of:

| Metric (per single-service story)                       | Baseline | Target          |
| ------------------------------------------------------- | -------- | --------------- |
| High-power agent turns on the happy path                | 3        | **2** (plan, implement) |
| Agent turns on a one-lint-failure path                  | 4        | **3**           |
| Distinct result schemas parsed by `dev`                 | 5+       | **3** (plan, impl, fix) |
| Lines under `coder/prompts/` that name a stack/tool     | many     | **0** (guarded) |
| Wall-clock, median story, happy path                    | measured | **≥ 30 % lower** |
| Stories that end `WorkflowFailed` on a budget           | 0        | 0 (unchanged)   |
| Fix-lap success rate (lap makes the gate green)         | measured | **not lower**   |

The last row is the one that can quietly go wrong: a cheaper fix lap that fails more often is
not an optimisation, it is a cost moved to the operator gate. It is tracked per
`FailureReport.source`, so a regression in one source (say `regression`) is visible on its own
and not averaged away by lint.

### Filled in after step 7 (Plan A's re-measure)

Same repo, same story, same model tier as the baseline, and the same starting commit for
every run: `expense-list` in `/tmp/bench-expense-split` from `3fa416f`, a single Go service.
Run-ids are `benchmarks/devlane.py` runs under that repo, re-derivable with
`devlane.py table --run-id <id>` long after the console output is gone.

| run | tree | turns | happy | repair | wall | cost |
| --- | ---- | ----: | ----: | ------ | ---: | ---: |
| `a12` | step 6 | 3 | 2 | 1 × `goal` | 11.0 min | $3.98 |
| `a13` | step 6 | 3 | 2 | 1 × `goal` | 13.3 min | $5.61 |
| `a14` | step 6 | 2 | 2 | — | 11.7 min | $4.64 |
| `a15` | step 6 | 3 | 3 | — (schema retry) | 14.5 min | $5.51 |
| `b1` | + role resolver | 3 | 2 | 1 × `goal` | 21.5 min | $8.86 |
| `b2` | + role resolver | 2 | 2 | — | 16.5 min | $5.61 |
| `b3` | + role resolver | 2 | 2 | — | 11.8 min | $4.74 |
| `c1` | today's HEAD | 5 | 2 | 1 × `refine-plan`, 2 × `test` | 23.2 min | $8.29 |

| Metric                                            | Baseline | Target       | Measured (A)                | |
| ------------------------------------------------- | -------- | ------------ | --------------------------- | - |
| High-power agent turns on the happy path          | 3        | 2            | **2** in seven of eight runs | ✅ |
| Agent turns on a one-failure path                 | 4        | 3            | **3**, three times (`a12`, `a13`, `b1`) | ✅ |
| Distinct result schemas parsed by `dev`           | 5+       | 3            | **3** lane schemas — plan, impl, fix | ✅ |
| Lines under `coder/prompts/` naming a stack/tool  | many     | 0 (guarded)  | **0**, `make check-prompt-agnostic` over 91 files | ✅ |
| Wall-clock, median story, happy path              | 22.7 min (n=1) | ≥ 30 % lower | **13.9 min — 39 % lower** (median of n=8) | ✅ |
| Stories ending `WorkflowFailed` on a budget       | 0        | 0            | **0**                       | ✅ |
| Fix-lap success rate, per `FailureReport.source`  | no data  | not lower    | `goal` 3/3, `test` 1/2 — **no baseline to be lower than** | ⚠️ |

Median cost tracks the same way: $6.22 baseline → **$5.56** median. The eighth run is
`a15`, whose happy path was three turns rather than two — a schema retry, described at the
end of this section, and fixed in workhorse since.

Three honesty notes the single-run version of this table did not carry.

**The schema row counts different things on each side unless you say which.** The baseline's
"5 agent results" included `OperatorResolution`, which is the operator gate and not a step of
the lane; the three above are `PlanResult`, `ImplResult` and `FixResult`. Like for like, the
count went 5 → 4 with `OperatorResolution` in it, or 4 → 3 without. Either way `ReuseResult`
and `FixLintResult` are gone and no `dev` turn parses a schema the fix loop does not reuse.

**n matters more than the best run.** Quoting `a14`'s 11.7 min alone would have claimed 48 %,
and the spread here is 11.0–23.2 min on an identical starting tree — wider than the effect
being measured. The median over every run is the defensible number, and the slowest run in
the set is the newest one.

**`c1` is that run, and it says what the remaining cost is.** On today's HEAD the lane still
spent two high-power turns getting to a plan and an implementation, and then three more on
repair: one `refine-plan`, because the planner wrote `plan_file` as the repo-relative
`docs/specs/expense-list/plan.md` where `validate_plan` resolves it under the spec directory
and so found nothing; and two `dev-fix` laps on the `test` gate, the first of which came back
before the second closed it. The plan-validation lap is an interface defect rather than a bad
plan — the same string is correct under one reading and unresolvable under the other — and it
cost a 203 s high-power turn. It is tracked as its own ledger item; it is not evidence about
turn count, and it is not excluded from the table either.

The fix-lap row remains owed rather than met, for the reason the baseline gave: no lap ran on
the baseline, so there is no rate to be "not lower" than. What is now on record is the A-side
rate itself — `goal` 3/3, `test` 1/2 — measured over laps that repaired the *code*, unlike
the earlier `goal` laps that were repairing the harness (untracked files invisible to the
gates, `00abb0c`; a promise written from the repo root but run in the service directory,
`a72b117`; a promised command that can never terminate, `d3ed91f`; a promised command with
its outcome written beside it, `68a3e35`). Step 11 measures it on a story seeded to fail its
gate once per source, which is the comparison this row actually wants.

One more turn was bought back after `a15`: it spent a third high-power turn on a schema
retry, because every field of a `returns=` model was a required output key and the implement
turn had sensibly omitted a branch-specific one (`d55ea6e`). It is a workhorse fix, not a
dev-flow one, so it only removes a way of losing the 2-turn happy path.

### Filled in after step 11 (Plan B's re-measure)

Same repo, same story, same starting commit, same model tier as every row above:
`expense-list` in `/tmp/bench-expense-split` from `3fa416f`. The two runs on the B-side tree
are `c1` (today's HEAD as of 07:09, before `e4e814a`) and `d1` (07:25, after it); both are
re-derivable with `devlane.py table --run-id <id>`.

| run | tree | turns | happy | repair | wall | cost |
| --- | ---- | ----: | ----: | ------ | ---: | ---: |
| `c1` | steps 8–10 | 5 | 2 | 1 × `refine-plan`, 2 × `test` | 23.2 min | $8.29 |
| `d1` | steps 8–10 + `e4e814a` | 4 | 2 | 2 × `test` | 16.0 min | $6.69 |

| Metric                                            | Baseline | Target       | Measured (B)                | |
| ------------------------------------------------- | -------- | ------------ | --------------------------- | - |
| High-power agent turns on the happy path          | 3        | 2            | **2** (`plan-story`, `implement-plan`) in both runs | ✅ |
| Agent turns on a one-failure path                 | 4        | 3            | **not measured on B** — neither run failed a gate exactly once | ⚠️ |
| Distinct result schemas parsed by `dev`           | 5+       | 3            | **3** — `PlanResult`, `ImplResult`, `FixResult` | ✅ |
| Lines under `coder/prompts/` naming a stack/tool  | many     | 0 (guarded)  | **0**, `make check-prompt-agnostic` | ✅ |
| Wall-clock, median story, happy path              | 22.7 min (n=1) | ≥ 30 % lower | **B claims nothing here** (n=2, both slower than A's median) | — |
| Stories ending `WorkflowFailed` on a budget       | 0        | 0            | **0**                       | ✅ |
| Fix-lap success rate, per `FailureReport.source`  | no data  | not lower    | `test` 2/4 on B, `goal` 3/3 on A — **no shared source, so no comparison** | ⚠️ |

Step 11 said B may claim only the turn-count and schema rows unless the table says otherwise.
The table does not say otherwise, and three of the seven rows are worth reading carefully.

**The happy path held at two turns, and `e4e814a` bought back the third.** `c1` spent a 203 s
high-power `refine-plan` lap because the planner wrote `plan_file` as the repo-relative
`docs/specs/expense-list/plan.md` while `validate_plan` and `ostler artifact vet` both resolve
it under the spec directory. `d1` is the same tree with that interface defect repaired, and
the lap is gone: four turns, not five, and no `refine-plan` at all. That is one run's evidence,
not a rate, but it is the run the fix was written for and it is on the record either way.

**B does not claim the wall-clock row and the table is why.** `c1` at 23.2 min is the slowest
run in the whole set and `d1` at 16.0 min the fourth-slowest; `c1` was already counted in step
7's median, and adding `d1` moves the overall median from 13.9 min (n=8) to 14.5 min (n=9) —
still 36 % under the 22.7 min baseline, but moving in the wrong direction. Two runs cannot
separate a real regression from the 11.0–23.2 min spread that an identical starting tree
already produces, so the honest reading is that A's median stands as the measured result and
B has not been shown to change it.

**The fix-lap row is still owed, and now for a second reason.** Step 7 left it owed because no
lap ran on the baseline. Step 11 was supposed to settle it "on a story seeded to fail its gate
once per source" — that story was never constructed. The bench at `3fa416f` seeds a lint-red
and a test-red defect in `member`, and the other sources (`goal`, `tdd`, `regression`) only
fire opportunistically, so what the two sides actually produced was `goal` laps on A and
`test` laps on B, with **no source appearing on both**. There is no per-source rate to compare
and averaging across sources is exactly what this row was written to prevent. What is on
record is each side's own rate: A `goal` 3/3, B `test` 2/4 — where both B laps are the same
shape, a first lap that came back and a second that closed the gate.

## Three invariants

1. **The workflow assumes nothing about where it is deployed.** No stack name, no tool name,
   no path convention, no test-framework idiom appears under `coder/prompts/` or `coder/*.py`.
   What is stack-shaped comes from the target repo at run time — its `agents.yml`, its packs,
   its skills, its installed prompts. This gets a guard, `make check-prompt-agnostic`, the way
   `check-no-env` and `check-no-giveup` guard their rules, because prose rots back.
2. **A node is a conversation, not a prompt.** A lane opens a session and sends turns into it;
   a turn is `(flow, role, payload)`. The implementer that built the change is the one that
   fixes it, in the same context, at a lower power. "Which prompt" is resolved from the
   library, not hard-bound in the flow; it resolves to a file named `<flow>-<role>.md`
   (e.g. `dev-implement.md`, `dev-fix.md`), with the payload rendered into it.
3. **The workflow owns the contract, the repo owns the body.** What stablemate renders is the
   envelope: provided inputs, the operator answer, the machine-readable result. What it does
   *not* author is how to test a Go service or bring up a Flutter emulator — that is the
   body, and the body comes from the library the repo installed.

Prompts stay context-staged. A stage that only applies when the workspace has two repos, or
when the plan lists codegen, or when an operator has answered, renders only then — Jinja
already does this and it is the right tool. What goes is the *unconditional* stack text, not
conditionality.

## A hypothesis this plan states out loud so step 1 can kill it

The plan assumes two things cost time: **the number of high-power turns** and **the briefing
each turn re-reads**. The first is almost certainly the larger. A 498-line prompt is ~7k
tokens; an 8.6-minute planner turn is overwhelmingly tool calls and reasoning over real code,
not reading the brief. So prompt-length reduction (invariant 1) is pursued for *ownership*
and *correctness* — the wrong stack's advice does active harm — and is **not** allowed to
claim a latency number. If the step-1 table shows briefing is under 10 % of turn time, the
de-prompting steps still happen, but the wall-clock target above is carried by turn-count
and the deterministic gates alone. Writing this down now is what stops a later "we cut
2,000 lines" from being reported as "we made it faster".

## The design

### One session per lane, turns picked by role

`Dev` opens `impl:<story>` once. It sends:

```
implement   flow=dev   power=high   payload: story, plan, instruction files
fix         flow=dev   power=low    payload: FailureReport            (lap 1)
fix         flow=dev   power=low    payload: FailureReport            (lap 2)
fix         flow=dev   power=high   payload: FailureReport            (lap 3, last)
→ Await                                                   (the operator, never a give-up)
```

The power ladder is low → low → high, not flat: the third lap gets the reasoning budget
because two cheap laps not clearing the same gate is evidence the fix is not local. A stalled
identical failure (same `FailureReport` hash twice running) skips straight to the high lap.

The same session receives `apply-review` findings from the review lane and `apply-qa-fixes`
findings from the QA lane — as `fix` turns with a different `FailureReport.source`. The
*judging* turns (review, QA audit, triage) stay on fresh sessions; a reviewer who inherited
the author's context is reviewing their own reasoning. That rule is already written in
`agent()`'s docstring and is kept.

**Session length is bounded.** A session that has implemented, fixed lint three times, applied
review and applied QA is long, and low power on a long context can be worse than high power on
a fresh one. The lane tracks turns-since-open; past `max_session_turns` (default 8) the next
`fix` opens a fresh session seeded with a Python-rendered digest (story, plan, the list of
files the session touched, the current `FailureReport`) rather than the full history. Per-lap
wall-clock is in telemetry so step 8 can see whether this threshold is right.

`FailureReport` is one schema — `{source, command, cwd, output, findings[], lap}` — and small
Python adapters produce it from lint output, CI logs, a verify command, a regression run, a
TDD check, review findings, QA findings. The fix turn sees one shape. Because it resumes a
conversation that already read the story, the plan and the skills, the fix prompt says none
of that again: it is the payload and "make it pass; report what you ran".

**Not every failure is the same shape, and the body is allowed to know that.** The eight
repair prompts being deleted carry some lane-specific knowledge worth keeping — a regression
means "reproduce, then revert-or-fix, never paper over"; a CI failure means "read the log for
the *first* red, not the last"; a review finding is a request, not a verdict, and may be
declined with a reason. That survives as a `{% if report.source == "regression" %}` stage in
the `fix` body, ≤ 8 lines per source. The ≤ 40-line target is for the source-independent core;
the body with every source block rendered is still well under what any single repair prompt is
today. What does *not* survive is any stack-specific advice in those blocks — that is the
repo's body, via a `fix` override in its `agents.yml`.

A resumed conversation is also what makes low power sufficient: the reasoning that needed
high power happened on the `implement` turn and is in the context.

### Goal setting: the turn states its exit condition, and the machine checks it

An agent turn does better work when it begins by writing down what "done" is and ends by
checking it. That is the useful core of `/goal`-style agentic goal setting. Where it goes in
this design matters, because the cheapest way to add it is also the most expensive:

- **Not a separate turn.** A goal-setting call before `implement` is a fourth high-power
  turn — the category this plan exists to remove. And on `fix` the goal is already a
  machine-produced object (`FailureReport` → "make this green"); restating it is ceremony.
- **A stage of the envelope, on `plan` and `implement` only.** The envelope opens with a
  short "before acting, state the exit condition: which acceptance criteria you will satisfy,
  which commands you expect to be green, which files you expect to touch". Three lines of
  contract, owned by stablemate, not by the body.
- **Emitted into the result schema, so it becomes evidence.** `ImplResult` gains
  `exit_conditions: {criteria[], commands[], files[]}` — what the turn *promised*. The
  deterministic gate after the turn compares promise to fact: commands it said would be green
  are run (from `agents.yml services`), files it said it would touch are diffed, criteria are
  carried forward to the review and QA lanes as the thing to check first. A gap is a
  `FailureReport{source: "goal"}` into the same fix loop — "you said `make test` would pass;
  it does not" — not a new state.

This is goal setting as a falsifiable claim rather than as a pep talk, and it costs no extra
agent call. It is also what makes the next section cheap.

### TDD: a repo-declared gate, not workflow prose

The argument for TDD with agents (Matt Pocock and others make it well) is not that red-green
is virtuous; it is that a failing test written first gives the agent a concrete,
machine-checked target and removes the "declare victory on a green build that tests nothing"
failure mode. That argument is good and this plan adopts it — as a mechanism, because as
prose ("write the test first — MANDATORY") it is exactly the scar tissue being deleted, the
model half-complies, and nothing can check it.

- **The repo declares it.** `agents.yml services.<type>.tdd: required | encouraged | off`.
  A Go API says `required`; a Pulumi stack or a docs service says `off`; a greenfield repo
  whose test harness does not exist yet says `encouraged` until genesis has scaffolded one.
  Invariant 3: whether this is a TDD repo is the repo's body, not the workflow's.
- **The machine checks it.** After `implement`, a deterministic node reads
  `ImplResult.tests_added[]` and the diff. `required` means: test files changed, *and* the
  declared `test` command was run red-then-green within the turn (the turn reports both runs
  in `exit_conditions.commands` with exit codes; the gate re-runs green to confirm). A miss is
  a `FailureReport{source: "tdd"}` — "no test covers this change; add one that fails without
  it" — into the same fix loop. `encouraged` logs the miss to telemetry and continues. `off`
  skips the node.
- **An exemption is a claim, not a flag.** The implement result may set
  `tests_added: []` with `no_test_reason: "..."`; the gate accepts it only for stories whose
  plan-context marks the service `docs`/`config`, otherwise it is a `tdd` failure with the
  reason quoted back. This keeps the escape hatch from becoming the default.
- **The body teaches the how; the gate enforces the whether.** How to write a table test in
  Go, or a widget test in Flutter, is the stack skill the repo installed; the implement body
  says only "if this repo requires TDD, the failing test is your first edit". Where TDD
  genuinely hurts — visual UI work, scaffolding, migrations — the repo says `off` for that
  service type and nothing pretends otherwise.

Because goal setting already makes the turn emit the commands it ran, TDD costs one more
adapter and one `services` key; it does not cost a prompt.

### Roles resolve to library prompts

The flow never names a file. It asks for a role:

```python
self.turn("implement", session=chain, power="high", args=...)
```

and a resolver maps `role → prompt` in order: the repo's `agents.yml` (`prompts: {fix:
go/fix-go-tests}`), then the packs the repo selected, then stablemate's defaults. The defaults
move *out of* `workflows/src/workhorse_workflows/coder/prompts/` and into the base library
beside `library/prompts/stablemate/implement-plan.md` that already exists there — one source
for the interactive command and the workflow turn. What stays in `workflows/` are the workflow
mechanics no repo should override: `resolve-operator.md`, the envelope, the settle/merge
prompts (git surgery, not code).

A prompt body is wrapped by the envelope at render time: provided inputs on top, exit-condition
stage, operator answer if any, result schema at the bottom. The body is free text the library
owns; the envelope is what the state machine parses.

**This relocation is the riskiest step and is sequenced last** (see "Two plans, not one").
It touches how the base library is fetched (`~/.cache/stablemate`), every prompt test fixture,
the `agents.yml` schema and the `check-public` sweep's idea of "base stands alone". It is a
project, not a step, and it does not get to claim the latency number.

### The repo declares its commands; Python runs them

`agents.yml` gains, per service type the repo has:

```yaml
services:
  go:      {test: "make test", lint: "make lint", smoke: "make smoke", codegen: "make gen", tdd: required}
  svelte:  {test: "pnpm test", lint: "pnpm lint", smoke: "pnpm dev:smoke", tdd: encouraged}
  docs:    {tdd: off}
```

Deterministic nodes run `test` and `lint` after the implement turn and after every fix turn;
their output *is* the next `FailureReport`. The prompt stops saying "run the tests — MANDATORY"
because the machine runs them, and stops naming `make lint` because it does not know the
command. This is the other agent's `verify_command`, owned by the repo instead of guessed by
the planner per story — and it is the only part of that diff worth keeping.

**A repo that has not declared a command gets a skipped gate, a log line, and a telemetry
counter** — not a guess. A missing `smoke` means the smoke step does not run; it does not mean
the prompt invents one. But "skipped gate" is also the silent-regression case: today's prompt
at least *tells* the model to test; tomorrow's says nothing and the gate is off. So:

- **Genesis writes the `services` block** when it scaffolds a repo. The greenfield benchmark
  (`greenfield-benchmark-app`) is the test: if the todo-app comes out of genesis with no
  `services`, this step is not done.
- **Farrier's doctor warns** when a repo has the coder workflow installed and a service marker
  (`go.mod`, `package.json`, `pubspec.yaml`, …) with no matching `services` entry. A repo can
  ignore it; it cannot be surprised by it.
- **The implement envelope shows the gate list it will run.** A turn told "after you finish I
  will run: (nothing declared)" has the same information the old prose gave it, in one line.

Where the guidance lives — which tool exercises a Flutter screen, what a healthy API boot looks
like — is the stack skill the repo installed, and the implement turn is pointed at it by the
instruction resolution that already exists.

### Dispatch from markers, and the agent returns the structure instead of writing a file

`plan-context.json` is the largest single chunk of `plan-story.md`: a planner writes, by hand,
which services exist, their type, their skills, their plan file, their build order. The repo
already knows the first three from `agents.yml` service markers and skill tags; Python
synthesizes the skeleton and the planner adds only what it decided — which services this story
touches, in what order, and the plan files. `ostler artifact vet plan-context` keeps its
schema, and the `qa_stack` field is renamed away from its near-homograph with `qa-stack.yml`
(`dev-workflow-qa-stack-schema-collision`) at the same time.

The deeper problem is *who authors the file*. Today the agent free-types a JSON document
under `<spec_dir>/`; Python `load_json`s it in four places (`validate_plan_context`,
`resolve_impl_context`, review's `get_affected_repos`, QA), rewrites it to normalise repo
names, and decodes slices into prompt args — and then the next prompts *also* say "if a
`plan-context.json` exists in the spec dir, read it" (`review-implementation.md:30`,
`plan-qa.md:76`), so the same data is parsed by the machine and re-read by an agent through
a tool call, and the two can disagree after the rewrite. Meanwhile `PlanResult` — the
structured, checkpointed output channel that already exists — carries only `{status,
summary}`. The "exists but has no `services` array" error path, the `rework_paths` lap and
the `qa_stack` homograph are all symptoms of an agent being the author of a machine-read
file.

**The agent returns it; the machine owns it.**

- `PlanResult` gains the fields (`services[]`, `implementation_order`, `shared_packages`,
  …). The planner fills a pydantic schema the checkpoint already validates; a malformed
  result is a parse retry, not a workflow state, so `validate_plan_context`'s shape checks
  and their rework lap disappear. Semantic checks (declared paths exist, order references
  known services) stay, as one deterministic gate feeding the `refine` loop.
- Python renders the *content* into later turns — the envelope's provided inputs — instead
  of a path plus "read it". The implementer gets its service's skills and plan file; the
  reviewer gets the affected repos; QA gets its slice. No turn spends a tool call
  discovering what the workflow already knows, and none can read a stale copy.
- The file survives only as a **projection** Python writes from the checkpointed value,
  where a reader outside the producing run needs it — the QA lane on a later run, `ostler
  artifact vet`, a human in the spec dir, docs. It is written one way and never parsed back
  by the lane that produced it.

The rule that falls out, applied across the coder: pass **content** when it is small,
structured and machine-owned — `plan-context`, `qa-okf-context`, `review-resolution`,
`backlog-items`, `FailureReport`; pass a **path** when it is large, free-form, or an artifact
the agent must edit in place — implementation plans, code, QA evidence with attachments. If
Python has a loader for it, it belongs in a result schema, not in a file the agent writes.
Two guards on the rule: the checkpoint is run state, not a doc store, so anything with a
cross-run reader still gets its projection on disk; and inline content costs tokens on every
turn it is rendered into, so the envelope renders only the slice each role needs, never the
whole dispatch.

### Dev has no rework loops of its own

`check_reuse`, `rework_reuse`, `validate_paths`/`rework_paths`, `lint`/`fix_lint`, and the
working tree's `verify`/`rework_verify`, `check_pointers`/`rework_pointers` all become the one
`fix` re-entry driven by a `FailureReport`, with one `max_fix_laps` and the power ladder above.
Plan-quality repair (`refine-plan`) stays — it is a different conversation about a different
artifact — but it is one role, `refine`, not three callers with three budgets. `dev`'s
`BUDGET_LABELS` shrinks from `(plan_rework, pointer_rework, lint_rework, verify_rework,
plan_blocks)` to `(plan_rework, fix_laps, plan_blocks)`. Exhausting `fix_laps` is an `Await`,
as the no-give-up rule requires; the counter is in the checkpoint so a resume continues the
same ladder.

The reuse question is real and is not dropped; it moves to where it is cheap: a short stage in
the implement body ("search before you build"), which the body owner may sharpen for their
stack, and a review-lane finding if it was missed. A dedicated high-power agent turn to ask
"does this already exist?" before any code is written was the single most expensive way to
ask it.

### The `check-prompt-agnostic` guard, concretely

A grep with a hard-coded list of stack words is both too loud (`make`, `test`, `lint` are
generic *and* stack-flavoured) and a list that publishes what it bans. The guard instead:

- reads its token list from `scripts/prompt_agnostic_tokens.txt` (tracked — these are public
  stack names, not private ones, so the `check-public` reasoning does not apply);
- matches **whole tokens, case-sensitive**, inside backticks or bare, and skips Jinja
  `{% if %}` blocks whose condition names a `service.type` — conditional stack text is
  allowed by design, unconditional is not;
- reports file:line and the matched token, and fails on any hit under `coder/prompts/` and
  `coder/**/*.py` outside a short per-file allowlist (the adapters that parse `go test`
  output legitimately know the word `go`).

It lands in the same commit the bodies move, and it is run by `make test`. Expect the first
run to be red on a dozen things nobody remembered were stack-shaped; that is the point.

## Risks, and what retires each

| Risk                                                                  | Retired by                                                                 |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Prompt trimming is reported as speed-up without evidence              | Hypothesis section; step 1 baseline; step 8 re-measure per turn            |
| One `fix` body loses regression/CI/review-specific knowledge           | `source`-conditional stages in the body; per-source fix-success metric     |
| Low power on a long session is worse than high on a fresh one         | `max_session_turns` + digest re-seed; per-lap time in telemetry            |
| Undeclared `services` means no gate and no prose → silent regression  | Genesis writes the block; farrier doctor warns; envelope names the gate list|
| Base-library relocation balloons the project                          | Sequenced into plan B, gated on plan A's numbers                           |
| `check-prompt-agnostic` is noisy or publishes a banlist               | Tracked public token file, conditional-block exemption, per-file allowlist |
| TDD gate blocks stories that cannot have tests                        | Repo-declared `tdd:` per service type; reasoned exemption, vetted          |
| Checkpoint param drift kills in-flight runs on reload                 | Removed `max_*_reworks` stay as deprecated, ignored fields for one release (`checkpoint-param-drift-breaks-reload`) |
| Agent-authored JSON drifts from what Python decoded                    | Structure returned in `PlanResult`; file is a Python-written projection      |
| Goal setting becomes another paragraph nobody checks                  | It is a result-schema field the gate compares to the diff and the runs     |

## Two plans, not one

The original eight steps were one list; five of them are cheap and carry the number, and two
are a separate project. Splitting them is what makes "confident in full success" honest.

### Plan A — fewer turns, machine-run gates (carries the latency target)

1. **Measure first.** A turn-level wall-clock table on `/tmp/bench-expense-split` from the
   run's telemetry: per turn, power tier, tokens in/out, tool calls, seconds; per story,
   happy-path turn count and fix-lap count. Every later step reports against it; the memory
   `feedback-measure-before-claiming-optimization` is the rule. *Done when:* the table is
   committed under `docs/plans/optimize-baseline.md`.
2. **Revert the working-tree diff** on `stable-bench` (keep a branch of it for the pointer
   helper and the TDD wording). *Done when:* `git status` is clean and `make test` is green.
3. **`FailureReport` + `fix` role + one session per lane** in `dev` only; lint is the first
   adapter, then verify and regression. The power ladder and `max_session_turns` land here.
   *Done when:* `dev`'s happy path is plan → implement → gates, `BUDGET_LABELS` is the
   three-tuple, and one-lint-failure path is three turns in the bench telemetry.
4. **`PlanResult` carries the structure**; `plan-context.json` becomes a Python-written
   projection; `validate_plan_context`'s shape checks and `rework_paths` go; downstream
   prompts lose every "read `plan-context.json`" line in favour of rendered content.
   *Done when:* no prompt under `coder/` names `plan-context.json` and the review/QA lanes
   read the projection only when the dev run is not the producer.
5. **`agents.yml` service commands** + deterministic test/lint/smoke nodes; genesis writes the
   block; farrier doctor warns; delete the corresponding "MANDATORY" prose. *Done when:* the
   bench repo's `services` block drives the gates and the todo-app comes out of genesis with
   one.
6. **Goal setting in the envelope + `goal` adapter**; **TDD gate** with the `tdd:` key.
   *Done when:* `ImplResult.exit_conditions` is populated on the bench and a deliberately
   test-less story is caught by the `tdd` gate and fixed by the same loop.
7. **Re-measure.** Same table, same stories. *Done when:* the success table above is filled
   in, row by row, and the fix-success-rate row is not lower per source.

### Plan B — ownership (carries the correctness argument; gated on A's table)

8. **Role resolver + envelope as a library concern**; move the default bodies to the base
   library; `check-prompt-agnostic` lands the same day the bodies move, or the text grows back.
   Source-conditional `fix` stages are rewritten against invariant 1 here.

   > **Done, with the relocation half rejected (2026-08-20).** The resolver, the envelope,
   > `check-prompt-agnostic` and the `agents.yml` `prompts:` override all landed. Moving the
   > defaults to the base library did not, and will not: a workflow distribution is
   > **standalone**. `workhorse-workflows` is installed on its own and a machine that never
   > ran farrier must run every story end to end, so defaults living in an optional install
   > would make that install load-bearing for every turn. The base library's prompts are the
   > other thing — commands farrier installs for a *person* to invoke. `library/prompts/coder/`
   > survives as an empty override slot an overlay may fill; resolving nothing is the ordinary
   > case. The step's own "riskiest, sequenced last" warning was about exactly this blast
   > radius, and the cheaper answer was to keep the bodies where they ship from (`52a30d6`).
9. **Dispatch from markers**; `qa_stack` rename.
10. Review and QA lanes re-enter the implementer session for their apply steps (this is where
   `max_session_turns` earns its keep; it was landed in A so B can lean on it).
11. Re-measure once more; B may claim only the turn-count and schema rows, never wall-clock,
    unless the table says otherwise.

    > **Done (2026-08-20).** The table is above, under *Filled in after step 11*. B claimed the
    > turn-count and schema rows and nothing else: the happy path held at two high-power turns
    > across `c1` and `d1`, `dev` parses three schemas, and `e4e814a` removed the one extra lap
    > `c1` had spent. The wall-clock row stays A's, and the fix-lap row stays owed — the
    > "seeded to fail once per source" story this step called for was never built, and the two
    > sides produced disjoint sources, so there is nothing to compare.

If A's re-measure does not hit the wall-clock target, B still happens — the ownership
argument stands on its own — but the shortfall is diagnosed from the table first, not papered
over by starting B.

## What this does not promise

It does not make the expense benchmark one minute by itself — the planner turn is still a
high-power turn reading real code. It makes the workflow stop paying for things that are not
its business, and it makes every remaining cost a line in the timing table with an owner. The
"small story fast lane" brainstormed earlier is deliberately not here: the goal is a workflow
that includes only what it needs, and a second lane is more workflow, not less. It also does
not promise that a repo with no `services` block and `tdd: off` everywhere gets a better
coder than today; it promises that such a repo is *told* so, by doctor and by envelope, rather
than discovering it in a review.
