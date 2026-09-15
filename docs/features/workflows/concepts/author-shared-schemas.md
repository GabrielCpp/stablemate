---
type: concept
slug: author-shared-schemas
title: Author shared schemas
---
# Author shared schemas

The shared schema package defines the typed values crossing author workflow node and agent
boundaries. All models inherit the same permissive reply behavior: every declared field has a
default, unknown keys are ignored, and null input values are removed before validation. The
package groups the main author graph, edit flows, survey flows, and parity configuration; the
format nodes linked below document the fields exposed by these contracts. `main.py` exports the
principal graph's node-return and agent-reply models listed below; the other schema modules are
separate source-layer groups.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/_base.py::AuthorResult` @9dc6216f013f
- tests: [author unit tests](../ops/author-unit-tests.md)
- detail: [author configuration](../author-config.md)
- detail: [author run context](../run-context.md)
- detail: [author step](../author-step.md)
- detail: [epic choice](../epic-choice.md)
- detail: [story choice](../story-choice.md)
- detail: [seeded story](../seeded-story.md)
- detail: [story mutation](../story-mutation.md)
- detail: [coverage defects](../coverage-defects.md)
- detail: [roadmap status](../roadmap-status.md)
- detail: [verification report](../verify-report.md)
- detail: [feedback](../feedback.md)
- detail: [pruned backlog result](../pruned.md)
- detail: [attempt ledger](../ledger.md)
- detail: [commit result](../committed.md)
- detail: [mockup result](../mockup-result.md)
- detail: [mockup gate](../mockup-gate.md)
- detail: [write epic result](../write-epic-result.md)
- detail: [write story result](../write-story-result.md)
- detail: [audit finding](../audit-finding.md)
- detail: [audit result](../audit-result.md)
- detail: [coverage review](../coverage-review.md)
- detail: [author edit intent](../edit-intent.md)
- detail: [resolved bullet](../resolved-bullet.md)
- detail: [epic edit snapshot](../epic-snapshot.md)
- detail: [seed snapshot](../seed-snapshot.md)
- detail: [story snapshot](../story-snapshot.md)
- detail: [milestone snapshot](../milestone-snapshot.md)
- detail: [seed change](../seed-change.md)
- detail: [story change](../story-change.md)
- detail: [epic edit plan](../epic-edit-plan.md)
- detail: [applied epic edit](../applied-epic-edit.md)
- detail: [epic edit review](../epic-edit-review.md)
- detail: [epic rewrite result](../epic-rewrite-result.md)
- detail: [author story choice](../story-choice.md)
- detail: [seeded story result](../seeded-story.md)
- detail: [story mutation result](../story-mutation.md)
- detail: [write story result](../write-story-result.md)
- detail: [survey shared library](survey-shared-library.md)
- detail: [parity configuration](../parity-config.md)
- detail: [survey configuration](../survey-config.md)
- detail: [survey inventory check](../inventory-check.md)
- detail: [survey expansion result](../expansion.md)
- detail: [survey unit pick](../unit-pick.md)
- detail: [survey split result](../split-result.md)
- detail: [survey mark result](../mark-result.md)
- detail: [survey record check](../record-check.md)
- detail: [survey verification result](../verify-result.md)
- detail: [survey partition check](../partition-check.md)
- detail: [survey emission result](../emit-result.md)
- detail: [survey plan reply](../plan-result.md)
- detail: [survey unit assessment reply](../unit-assessment.md)
- detail: [survey record-fix reply](../record-fix.md)
- detail: [survey partition proposal reply](../partition-proposal.md)
- detail: [survey operator resolution reply](../survey-operator-resolution.md)

## Methods

### _drop_nulls
- sig: `_drop_nulls(data: Any) -> Any`
- does: removes dictionary entries whose values are null before model validation
- verify: removed(subject="null-valued entries in the author schema input mapping")
- verify: count(subject="author schema null filtering", equals=1)
- returns: the filtered mapping or the original non-mapping input
- verify: count(subject="author schema validator inputs", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/_base.py::AuthorResult._drop_nulls` @9dc6216f013f

## Schema modules

The package's public models are grouped by source module. `main.py` supplies node returns and
agent replies for the principal author graph; `edit.py` supplies the edit intent and resolved
source bullet, the epic/seed/story/milestone snapshots, projected seed and story changes, the
replacement plan, the applied result, and the review and rewrite replies; `survey.py` supplies
survey node returns and agent replies; and `parity.py` supplies the separate parity configuration.
The edit plan contains seed and story change formats, while an epic snapshot contains seed,
story, and milestone snapshot formats. Their complete field contracts are the existing format
nodes reached from the author surfaces and subflows.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Defects` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RoadmapStatus` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::VerifyReport` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Feedback` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Pruned` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Ledger` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Committed` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StorySplit` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteStoryResult` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditFinding` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::CoverageReview` @e0c7b3335724
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::ResolvedBullet` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::MilestoneSnapshot` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditReview` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicRewriteResult` @ddad101f4da9
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::InventoryCheck` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::Expansion` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SplitResult` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordCheck` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::VerifyResult` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionCheck` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PlanResult` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitAssessment` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionProposal` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution` @f79c1c007a97
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig` @9c1c30dc1201
