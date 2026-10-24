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
principal graph's node-return and agent-reply models listed below. The PM's verdict, finding and receipt models live in the `pm` package, documented in [author PM review](author-pm-review.md); the other schema modules are
separate source-layer groups.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/_base.py::AuthorResult` @6a7046575304
- tests: [author unit tests](../ops/author-unit-tests.md)
- detail: [author configuration](../formats/author-config.md)
- detail: [author run context](../formats/run-context.md)
- detail: [story choice](../formats/story-choice.md)
- detail: [seeded story](../formats/seeded-story.md)
- detail: [coverage defects](../formats/coverage-defects.md)
- detail: [milestone status](../formats/milestone-status.md)
- detail: [verification report](../formats/verify-report.md)
- detail: [feedback](../formats/feedback.md)
- detail: [promoted record result](../formats/promoted.md)
- detail: [attempt ledger](../formats/ledger.md)
- detail: [commit result](../formats/committed.md)
- detail: [mockup result](../formats/mockup-result.md)
- detail: [mockup gate](../formats/mockup-gate.md)
- detail: [write epic result](../formats/write-epic-result.md)
- detail: [write story result](../formats/write-story-result.md)
- detail: [author edit intent](../formats/edit-intent.md)
- detail: [register listing](../formats/register-listing.md)
- detail: [epic edit snapshot](../formats/epic-snapshot.md)
- detail: [seed snapshot](../formats/seed-snapshot.md)
- detail: [story snapshot](../formats/story-snapshot.md)
- detail: [milestone snapshot](../formats/milestone-snapshot.md)
- detail: [seed change](../formats/seed-change.md)
- detail: [story change](../formats/story-change.md)
- detail: [epic edit plan](../formats/epic-edit-plan.md)
- detail: [applied epic edit](../formats/applied-epic-edit.md)
- detail: [epic rewrite result](../formats/epic-rewrite-result.md)
- detail: [author story choice](../formats/story-choice.md)
- detail: [seeded story result](../formats/seeded-story.md)
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
- code: `workflows/src/workhorse_workflows/author/shared/schemas/_base.py::AuthorResult._drop_nulls` @6a7046575304

## Schema modules

The package's public models are grouped by source module. `main.py` supplies node returns and
agent replies for the principal author graph; `edit.py` supplies the edit intent and the
register listing, the epic/seed/story/milestone snapshots, projected seed and story changes, the
replacement plan, the applied result, and the review and rewrite replies; `survey.py` supplies
survey node returns and agent replies; and `parity.py` supplies the separate parity configuration.
The edit plan contains seed and story change formats, while an epic snapshot contains seed,
story, and milestone snapshot formats. Their complete field contracts are the existing format
nodes reached from the author surfaces and subflows.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Filled` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::ContractDigest` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::UnfinishedRow` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Completion` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Defects` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MilestoneStatus` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::VerifyReport` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Feedback` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Promoted` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Ledger` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Committed` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StorySplit` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteStoryResult` @1afa9c641e4e
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::RegisterListing` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::MilestoneSnapshot` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicRewriteResult` @f582abc9a049
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::InventoryCheck` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::Expansion` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SplitResult` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordCheck` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::VerifyResult` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionCheck` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PlanResult` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitAssessment` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionProposal` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution` @59f51b5b79f1
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig` @40a9cc4079c3
