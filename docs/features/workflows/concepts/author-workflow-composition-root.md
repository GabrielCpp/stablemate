---
type: concept
slug: author-workflow-composition-root
title: Author workflow composition root
---
# Author workflow composition root

The `workhorse-author` console script imports this module and calls `main`. Its registry is the
single catalogue of the Author machine: a bare run enters `Author`, while named flows select a
separate machine. The default path implements the [roadmap intake](../flows/author-roadmap-intake.md);
the two direct editing machines implement [epic edit](../flows/author-epic-edit.md) and
[story edit](../flows/author-story-edit.md).

The registry is rooted at the `workhorse_workflows.author` package so prompt paths and repository
flavor lookup remain relative to the whole workflow, rather than the default flow's `main`
subpackage. It contributes the main, survey, epic-edit, story-edit, milestone, epic-split,
epic-author, story-author, and story-split node blueprints. It exposes ten named subflows:
`surveyor`, `parity-surveyor`, `epic-edit`, `story-edit`, `milestone`, `epic-split`, `epic-author`,
`story-split`, `story-author`, and `finalize`. The deterministic dry-run registry supplies a valid
reply for each prompt role, including approval/complete outcomes for planning and review turns,
an answered decision for resolver turns, and the explicit `design-mockup` skipped outcome.

- code: `workflows/src/workhorse_workflows/author/workflow.py`
- code: `workflows/src/workhorse_workflows/author/workflow.py::workflow`
- code: `workflows/src/workhorse_workflows/author/workflow.py::main`
- code: `workflows/src/workhorse_workflows/author/workflow.py::__all__`
- tests: `workflows/tests/author/test_workflow.py::test_every_flat_stage_is_directly_registered`
- detail: [Author roadmap intake flow](../flows/author-roadmap-intake.md)
- detail: [Author epic-edit flow](../flows/author-epic-edit.md)
- detail: [Author story-edit flow](../flows/author-story-edit.md)
- detail: [Author story-split flow](../flows/author-story-split.md)
- detail: [Author story-author flow](../flows/author-story-author.md)
- detail: [author main composition layers](author-main-composition-layers.md)
- detail: [author shared survey blueprint](author-shared-survey-blueprint.md)
- detail: [author shared paths](author-shared-paths.md)
- detail: [author shared schemas](author-shared-schemas.md)
- detail: [author entry point responsibilities](author-entry-point-responsibilities.md)
- detail: [author main view selection](author-main-view-selection.md)
- detail: [author epic split subflow](author-epic-split-subflow.md)
- detail: [author story-split subflow](story-split-subflow.md)
- detail: [author story-author subflow](author-story-author-subflow.md)
- detail: [author main dry-run stubs](author-main-dry-run-stubs.md)
- detail: [workflow kit export surface](workflow-kit-export-surface.md)
