---
type: flow
slug: coder-qa
title: Coder QA flow
---
# Coder QA flow

- The `Qa` machine resolves one authored story, rebuilds the QA obligation packet from the
  implementation diff, plans and runs the story's QA scenarios, audits the evidence, and either
  repairs the owned product/harness, reports a development-target result, or returns a bounded
  result to its parent. It is entered by Coder or directly with `workhorse-coder run qa`.
- Inputs include the story slug, optional docs/workspace and epic selectors, operator mode,
  target environment, stop-at-first-verdict measurement mode, inherited triage scope, and the
  preexisting worktree snapshot. Ambient repository paths are injected by the workflow engine.
- `target_env=local` permits product and setup repair; `target_env=dev` reports findings instead
  of editing code and reports a passing result after the same binding gates.
- `stop_at_first_verdict=true` reports the first product verdict as `inconclusive` after the
  deterministic evidence gate, while still classifying environment failures and allowing stack
  setup to be repaired.
- start: the configured story slug resolves to a readable story path
- verify: count(subject="resolved QA story contexts", equals=1)
- start: the QA context is rebuilt from the story's implementation diff and affected repositories
- verify: count(subject="QA obligation context builds", equals=1)
- steps:
  - [setup](#setup)
  - [context](#context)
  - [stack](#stack)
  - [plan](#plan)
  - [run-and-assess](#run-and-assess)
  - [evidence-and-audit](#evidence-and-audit)
  - [verdict-routing](#verdict-routing)
  - [feedback-and-regression](#feedback-and-regression)
  - [operator-resolution](#operator-resolution)
- end: a local story passes evidence, audit, sentinel, and regression gates and returns `status="passed"`
- verify: count(subject="passed QA flow results", equals=1)
- end: a product failure, rescope, development-target report, replan, or operator-gated block is returned without silently approving the story
- verify: count(subject="non-passing QA flow results", equals=1)
- detail: [coder main flow](coder-main.md)
- code: `workflows/src/workhorse_workflows/coder/qa/flow.py::Qa`
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_through_every_gate`
- tests: `workflows/tests/coder/qa/test_flow.py::test_an_unmappable_packet_is_repaired_and_rebuilt`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_failing_run_is_fixed_one_scenario_at_a_time`
- tests: `workflows/tests/coder/qa/test_flow.py::test_audit_refuting_on_a_product_test_gap_sends_the_fixer_not_the_planner`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_run_killed_mid_audit_resumes_on_the_audit`

The checkpointed `QaLoop` carries the QA result, context and plan diagnostics, assessment and
audit records, repair counters, failure fingerprints, setup-problem bundles, regression flags,
operator escalations, and docs-recheck state. The loop is rebuilt at `build_context` after any
product, feedback, regression, or grounding change, so the plan always answers the current diff.
The QA and plan wall-clock budgets are advisory telemetry; bounded repair ceilings, repeated
refusal detection, and operator gates decide whether work continues.

## Steps

### setup

The flow resolves the story slug, story path, spec directory, QA directory, and inherited
conversation. An empty or unresolved story raises `WorkflowFailed` before an agent turn rather
than producing an exhausted verdict. The flow resets its QA-specific session chains when it
starts and again when it ends.

### context

The flow clears prior QA evidence, resolves implementation context and affected repository paths,
optionally resolves story-source provenance, detects the OKF book, and builds an obligation packet
from the story diff, using the preexisting worktree snapshot to exclude unrelated dirt. An invalid
or unmappable packet receives up to `MAX_CONTEXT_REWORKS` low-power context repairs; a repaired
packet is rebuilt and revalidated. An exhausted or refused repair enters the operator gate.

### stack

`ensure_stack` runs before plan authoring. A ready stack or a book that serves no surface advances
to planning. A served surface with no declared stack, or a stack that fails to boot, enters the
bounded setup-fix loop; an identical blocked requirement bundle escalates instead of repeating.
Setup repair receives the verification setup, declared fixtures, QA run plan, runtime interpreter,
and the current block notes. `MAX_SETUP_REWORKS` bounds setup repairs.

### plan

The flow adopts an existing `qa_plan.py` only when its lint and obligation validation pass against
the rebuilt packet. Otherwise the first draft is authored by the QA planner and later laps edit
only cited portions of that plan. Lint and validation run before the suite; named riskiest draft
scenarios and named failed scenarios must pass their dry-run gate before a full run. Schema repairs
and semantic plan repairs have separate counters, share `MAX_TOTAL_PLAN_LAPS`, and identical
refusals enter the operator gate. Wall-clock overruns annotate the repair brief but do not end a
plan that can still be validated.

### run-and-assess

The validated plan runs once through `run_qa_plan`; a killed run resumes at assessment rather than
rerunning the suite. A passed run advances to evidence verification. A failed run is assessed
unless first-verdict mode reports it immediately as `inconclusive`. A blocked run is classified
for setup or plan repair. The assessment turn distinguishes confirmed success, plan extension or
repair, product failure, environment failure, and objective-not-reached outcomes; findings are
routed by closed scope (`product-test`, `plan`, or `stack`).

### evidence-and-audit

The evidence gate fails closed when the runner's required artifacts or evidence map are missing or
invalid. A valid pass is then audited adversarially unless first-verdict mode skips repair-only
auditing. A standing audit requires verdict `stands` with refutation class `none`. A product
contradiction becomes a QA failure; other refutations are routed to the product-test, plan, or
stack owner, while plan-only audit blocking stops after `MAX_BLOCKING_AUDITS` and is filed as
backlog work.

### verdict-routing

Backlog filing is best-effort and runs for both pass and failure. A confirmed pass proceeds to
feedback. A failed result enters triage, where in-AC defects use the QA fix loop and scope changes
return `status="rescope"` to development with docs recheck required. A product-class failure can
return `status="refix"` to development while its triage scope remains available for bounding.
In local mode, QA rework is bounded by `MAX_QA_REWORKS`, with one evidence-only bonus pass; a
repeated identical run failure switches once between plan repair and code repair before gating.
Budget exhaustion always enters the operator gate rather than silently ending the story.

### feedback-and-regression

After a pass the inbox is polled once. An operator note is applied as one low-power QA fix and
rebuilds context; no note advances to regression detection. Declared regression suites run after
the primary pass. A green or skipped regression finalizes unless a preceding regression fix
invalidated primary evidence, in which case context is rebuilt for one re-QA. Blocked or errored
regression setup uses the setup loop; failed regression suites receive up to
`MAX_REGRESSION_FIXES`, then fall into the ordinary QA fix loop.

### operator-resolution

QA blocks are counted at the common gate. In `auto` mode, at most `MAX_QA_BLOCKS` resolver turns
may apply an answer grounded in an existing decision, convention, or acceptance criterion; human
and operator modes await directly, and later blocks also await directly. An epic-scoped answer
returns `status="replan"`; a story-scoped answer is applied as a low-power QA fix and rebuilds
context. A refused report or fix is escalated without spending another repair lap, and report
write failures resume the same report state rather than re-QAing an already judged story.

The flow's own deterministic and agent-backed operations are implemented by the QA node modules,
evidence and hygiene modules, regression module, and QA checkpoint schemas. Those bounded source
groups are the next descent items.
