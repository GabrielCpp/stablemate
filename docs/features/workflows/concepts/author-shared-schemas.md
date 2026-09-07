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

- code: `workflows/src/workhorse_workflows/author/shared/schemas/_base.py::AuthorResult`
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
- code: `workflows/src/workhorse_workflows/author/shared/schemas/_base.py::AuthorResult._drop_nulls`

## Schema modules

The package's public models are grouped by source module. `main.py` supplies node returns and
agent replies for the principal author graph; `edit.py` supplies the edit intent and resolved
source bullet, the epic/seed/story/milestone snapshots, projected seed and story changes, the
replacement plan, the applied result, and the review and rewrite replies; `survey.py` supplies
survey node returns and agent replies; and `parity.py` supplies the separate parity configuration.
The edit plan contains seed and story change formats, while an epic snapshot contains seed,
story, and milestone snapshot formats. Their complete field contracts are the existing format
nodes reached from the author surfaces and subflows.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Defects`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RoadmapStatus`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::VerifyReport`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Feedback`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Pruned`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Ledger`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Committed`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StorySplit`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteStoryResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditFinding`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::CoverageReview`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::ResolvedBullet`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::MilestoneSnapshot`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditReview`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicRewriteResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::InventoryCheck`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::Expansion`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SplitResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordCheck`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::VerifyResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionCheck`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PlanResult`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitAssessment`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionProposal`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`
