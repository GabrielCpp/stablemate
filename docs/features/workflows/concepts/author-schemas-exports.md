---
type: concept
slug: author-schemas-exports
title: Author schemas exports
---
# Author schemas exports

The package initializer re-exports all agent reply models and node return models used by the
author workflow, organized by the workflow's sub-flows: main configuration, intake, epic
selection, planning, coverage validation, artifact gates, story processing, surveyor intake,
and parity configuration. The initializer imports from each subject module and does not add
another registration target; the model implementations remain documented at their declaring
modules.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/__init__.py::__all__`
- detail: [Author main package](author-main-package.md)

## Fields

### __all__

The explicit export list is the complete import surface consumed by the author workflow's
main flow and all sub-flows that share these models. It includes models for run context,
configuration validation, audit and coverage reviews, epic and story selection and mutation,
seeding and snapshots, edit operations, survey operations, and parity configuration.

- type: `list[str]`
- default: `['AuditFinding', 'AuditResult', 'AuthorStep', 'AppliedEpicEdit', 'AuthorResult', 'Committed', 'Config', 'CoverageReview', 'Defects', 'EmitResult', 'EditIntent', 'EpicEditPlan', 'EpicEditReview', 'EpicRewriteResult', 'EpicSnapshot', 'EpicChoice', 'Expansion', 'Feedback', 'InventoryCheck', 'Ledger', 'MarkResult', 'MockupGate', 'MockupResult', 'MilestoneSnapshot', 'OperatorResolution', 'ParityConfig', 'PartitionCheck', 'PartitionProposal', 'PlanResult', 'Pruned', 'ResolvedBullet', 'RoadmapStatus', 'RecordCheck', 'RecordFix', 'RunContext', 'SeededStory', 'SeedChange', 'SeedSnapshot', 'SplitResult', 'StoryChoice', 'StoryChange', 'StoryMutation', 'StorySnapshot', 'StorySplit', 'SurveyConfig', 'UnitAssessment', 'UnitPick', 'VerifyReport', 'VerifyResult', 'WriteEpicResult', 'WriteStoryResult']`
- required: true
- semantics: importing the package exposes exactly the listed models from the author workflow's schemas
- verify: count(subject="author schemas exports", equals=46)

