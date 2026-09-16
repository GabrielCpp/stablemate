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
- detail: [author configuration](../formats/author-config.md)
- detail: [author run context](../formats/run-context.md)
- detail: [author step](../formats/author-step.md)
- detail: [epic choice](../formats/epic-choice.md)
- detail: [story choice](../formats/story-choice.md)
- detail: [seeded story](../formats/seeded-story.md)
- detail: [story mutation](../formats/story-mutation.md)
- detail: [coverage defects](../formats/coverage-defects.md)
- detail: [roadmap status](../formats/roadmap-status.md)
- detail: [verification report](../formats/verify-report.md)
- detail: [feedback](../formats/feedback.md)
- detail: [pruned backlog result](../formats/pruned.md)
- detail: [attempt ledger](../formats/ledger.md)
- detail: [commit result](../formats/committed.md)
- detail: [mockup result](../formats/mockup-result.md)
- detail: [mockup gate](../formats/mockup-gate.md)
- detail: [write epic result](../formats/write-epic-result.md)
- detail: [write story result](../formats/write-story-result.md)
- detail: [audit finding](../formats/audit-finding.md)
- detail: [audit result](../formats/audit-result.md)
- detail: [coverage review](../formats/coverage-review.md)
- detail: [author edit intent](../formats/edit-intent.md)
- detail: [resolved bullet](../formats/resolved-bullet.md)
- detail: [epic edit snapshot](../formats/epic-snapshot.md)
- detail: [seed snapshot](../formats/seed-snapshot.md)
- detail: [story snapshot](../formats/story-snapshot.md)
- detail: [milestone snapshot](../formats/milestone-snapshot.md)
- detail: [seed change](../formats/seed-change.md)
- detail: [story change](../formats/story-change.md)
- detail: [epic edit plan](../formats/epic-edit-plan.md)
- detail: [applied epic edit](../formats/applied-epic-edit.md)
- detail: [epic edit review](../formats/epic-edit-review.md)
- detail: [epic rewrite result](../formats/epic-rewrite-result.md)
- detail: [author story choice](../formats/story-choice.md)
- detail: [seeded story result](../formats/seeded-story.md)
- detail: [story mutation result](../formats/story-mutation.md)
- detail: [write story result](../formats/write-story-result.md)
- detail: [survey shared library](survey-shared-library.md)
- detail: [parity configuration](../formats/parity-config.md)
- detail: [survey configuration](../formats/survey-config.md)
- detail: [survey inventory check](../formats/inventory-check.md)
- detail: [survey expansion result](../formats/expansion.md)
- detail: [survey unit pick](../formats/unit-pick.md)
- detail: [survey split result](../formats/split-result.md)
- detail: [survey mark result](../formats/mark-result.md)
- detail: [survey record check](../formats/record-check.md)
- detail: [survey verification result](../formats/verify-result.md)
- detail: [survey partition check](../formats/partition-check.md)
- detail: [survey emission result](../formats/emit-result.md)
- detail: [survey plan reply](../formats/plan-result.md)
- detail: [survey unit assessment reply](../formats/unit-assessment.md)
- detail: [survey record-fix reply](../formats/record-fix.md)
- detail: [survey partition proposal reply](../formats/partition-proposal.md)
- detail: [survey operator resolution reply](../formats/survey-operator-resolution.md)

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
