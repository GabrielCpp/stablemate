---
type: flow
slug: author-surveyor
title: Author surveyor
---
# Author surveyor

The surveyor is a subflow of the author workflow, invoked when the author runs in `surveyor` mode.
It answers one cross-cutting concern exhaustively: across a frozen rubric, it enumerates every
unit (screen, CLI, endpoint, or custom division) and checks whether each adheres to the stated
rules, producing an ordered backlog of findings grouped into work items. The flow is bounded by
operator gates at three critical junctures — when granularity planning fails, when coverage
verification fails, and when clustering the findings fails — but it never gives up autonomously:
every block escalates to the operator context for human decision or resolution, checkpointed and
resumable.

- start: the author runs with `mode="surveyor"`.
- start: a readable `rubric` path exists under `survey_dir`.
- start: survey artifacts (inventory, rules, findings records, partition, manifest) are either absent (first run) or present and consistent (resumed run).
- steps:
  - [plan granularity](#plan-granularity)
  - [expand and freeze inventory](#expand-and-freeze-inventory)
  - [per-unit assessment loop](#per-unit-assessment-loop)
  - [verify exhaustive coverage](#verify-exhaustive-coverage)
  - [cluster findings into work items](#cluster-findings-into-work-items)
  - [emit backlog and manifest](#emit-backlog-and-manifest)
- end: the survey has produced a durable backlog (`backlog.yml`) and unit manifest, representing an exhaustive assessment of the rubric against the repo, with every finding attributed to a work item and every work item traceable to at least one non-clean unit.
- verify: persists(subject="the survey backlog and manifest")
- verify: persists(subject="the frozen unit inventory")
- verify: unchanged(subject="the unit inventory after coverage verification")
- detail: [surveyor operator resolution field roles](../concepts/surveyor-operator-resolution-field-roles.md)
- detail: [author-surveyor subflow](../concepts/author-surveyor-subflow.md)
- tests: `workflows/tests/author/test_workflow.py::test_surveyor_produces_backlog_and_manifest`

## Plan granularity

Before any unit is enumerated, the surveyor invokes an agent to decide what constitutes a unit in
this rubric, in this repo. The agent reads the rubric and any existing rules file, and produces a
set of rules. If no frozen inventory exists, the planner runs; if a frozen inventory already
exists (a prior run or a resumed run), the planner is skipped — the survey must consume the list
already materialized.

The planner is bounded by `MAX_PLAN_REWORKS = 2` autonomous retries when expansion fails; after
two failures the block escalates to the operator gate. When `operator_mode = "auto"`, the
resolver agent investigates and writes findings; when `operator_mode = "human"`, the block goes
straight to the context file for manual decision.

Plan stage is implemented by `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.plan`,
which invokes an agent against `surveyor/prompts/plan-units.md`, and
`workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.expand`, which materializes
the frozen inventory.

## Expand and freeze inventory

Once granularity is decided, the surveyor materializes the frozen unit list by reading the rules
and enumerating units. If this is the first run, the list is new. If a frozen inventory already
exists (from a prior run or a resume), the new expansion is verified to be identical — a silent
mismatch would corrupt the coverage claim.

Expansion is bounded by `MAX_PLAN_REWORKS = 2` autonomous retries; like the planner, failures
escalate to the operator gate after two attempts. An expansion that yields zero units is a
granularity failure (the rules are too narrow), not a valid "nothing to survey" outcome, so it
goes back to the planner.

## Per-unit assessment loop

Once the unit inventory is frozen, the surveyor enters a loop that processes each unit until none
remain. For each unit, it assesses whether the unit adheres to the rubric, writes a finding
record, validates the record, and marks the unit as completed (or blocked if validation fails
after bounded repair). A split failure does not wedge the survey — the unit is marked as `blocked`
and the loop continues.

The per-unit loop is bounded by `MAX_RECORD_FIXES = 2` repair attempts; a unit that cannot be
fixed is recorded as blocked and the loop moves to the next unit. This ensures no unit can cause
the survey to wedge.

Assessment is implemented by `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.assess`,
which invokes an agent against `surveyor/prompts/assess-unit.md`. Validation is implemented by
`workflows/src/workhorse_workflows/author/shared/survey/records.py::validate_record`.

## Verify exhaustive coverage

Once every unit in the frozen inventory has been marked (either `completed`, `blocked`, or
`split-failed`), the surveyor verifies that coverage is exhaustive: all units are accounted for,
no units are missing, and the pending set is empty.

The coverage gate is bounded by `MAX_VERIFY_RESOLVES = 2` autonomous resolutions; after two
resolutions all later failures escalate to the human. Unlike the plan and partition gates, the
verify gate does not reset its counter on retry — the cumulative resolve counter applies across
all coverage verifications in the run.

Verification is implemented by `workflows/src/workhorse_workflows/author/shared/survey/records.py::verify_records`.

## Cluster findings into work items

Once coverage is verified, the surveyor invokes an agent to partition the findings into work
items. The partition represents the unit-to-work mapping: each work item claims at least one
non-clean unit, and every non-clean unit is claimed by at least one work item (lossless). The
partition is validated to ensure no orphans exist.

The partition gate is bounded by `MAX_PARTITION_REWORKS = 3` autonomous retries and
`MAX_PARTITION_RESOLVES = 2` autonomous resolutions; after exhausting the budget the block
escalates to the operator.

Partitioning is implemented by `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.partition`,
which invokes an agent against `surveyor/prompts/partition-findings.md`.

## Emit backlog and manifest

Once the partition is validated, the surveyor emits two durable artifacts: a backlog of work items
derived from the partition, and a unit manifest recording the disposition of every unit. Emission
is not bounded — a failure here is fatal to the survey and escalates as a workflow error.

Emission is implemented by `workflows/src/workhorse_workflows/author/surveyor/nodes/partition.py::emit_artifacts`.

## Operator gates

The flow has three operator gates where blocks escalate to human decision or automatic resolution:

- **Plan gate** — when granularity planning or expansion fails after `MAX_PLAN_REWORKS = 2`
  autonomous retries. Implemented by `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.resolve_plan`,
  which invokes an agent against `surveyor/prompts/resolve-operator.md`.
- **Coverage gate** — when coverage verification fails after `MAX_VERIFY_RESOLVES = 2` autonomous
  resolutions. Implemented by `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.resolve_verify`.
  Unlike the other gates, this one does not reset its counter on retry — the cumulative resolve
  budget applies across all coverage verifications in the run.
- **Partition gate** — when partitioning fails after `MAX_PARTITION_REWORKS = 3` autonomous
  retries and `MAX_PARTITION_RESOLVES = 2` resolutions. Implemented by
  `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.resolve_partition`.

At each gate, when `operator_mode = "auto"`, an agent with `power: high` and unbounded timeout
investigates the block and writes findings to the operator context file. The flow then returns to
`Await`. On resume, the flow re-enters the blocked state so it re-reads any updated context or
artifacts and retries. When `operator_mode = "human"`, every block goes straight to the context
file for manual decision.

All three resolvers invoke an agent against `surveyor/prompts/resolve-operator.md`.
