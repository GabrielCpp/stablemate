---
type: concept
slug: author-epic-edit-prompt-contracts
title: Author epic edit prompt contracts
---
# Author epic edit prompt contracts

The `epic_edit` flow renders nine agent turns. Planning and review turns are read-only; deterministic
nodes validate and apply graph changes between turns. Story authoring turns write only the selected
story's artifacts, while all turns return typed JSON consumed by the next state. The feature book is
always read-only to these prompts.

- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/plan-epic-edit.md`
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/refine-epic-edit-plan.md`
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/review-epic-edit-plan.md`
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/rewrite-epic-edit.md`
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/design-mockup.md`
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/write-story.md`
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/rework-story.md`
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/audit-story.md`
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/review-coverage.md`
- detail: [author epic edit subflow](author-epic-edit-subflow.md)

## Prompt Contracts

### Plan turns
`plan-epic-edit.md` receives the binding intent, current snapshot, epic directory, configured
backlog, feature-book directory, and optional epic context. It must return one complete `EpicEditPlan`
with journey, seed, story, deletion, affected-story, and notes data. It must not edit files.

`refine-epic-edit-plan.md` receives the same baseline, the rejected plan, and coded validation
findings. It returns a complete replacement `EpicEditPlan` that fixes every finding without weakening
the requested operation or mutating files.

### Review and rewrite turns
`review-epic-edit-plan.md` receives the intent, snapshot, and statically valid plan. It returns
`approved`, `needs_rework`, or `blocked` with notes and makes no repository change.

`rewrite-epic-edit.md` receives the intent, approved plan, pre-edit snapshot, surviving epic directory,
and prior validation findings. It may rewrite only human-owned epic prose before `## Seeds`, preserving
the `Seeds` and `Stories` sections, and returns `complete` or `blocked` with notes.

### Story turns
`design-mockup.md` runs only for a frontend affected story. It receives the epic, story identity and
directories, feature-book directory, and epic directory. It may write only the story-local
`mockup.html`; failure returns an empty mockup path and does not block authoring.

`write-story.md` receives the selected story identity, epic, feature-book directory, and optional
mockup path. It writes only the story planning artifact and returns `WriteStoryResult`; a product or
scope question returns `blocked` with notes.

`rework-story.md` receives the selected story, validation or audit findings, operator feedback, and
optional prior attempts and mockup path. It repairs only the named findings in the story artifact
and returns the same `WriteStoryResult` shape, including `blocked` for an unresolved scope decision.

`audit-story.md` receives the selected story identity and feature-book directory. It writes only the
story-local audit artifact and returns `AuditResult`; an empty findings list is the pass condition.

### Coverage turn
`review-coverage.md` receives the epic name, epic directory, backlog, and configured planning rules.
It reviews whether the deterministic coverage result is granular and complete, returns `ok`,
`gaps`, or `blocked`, and does not edit repository files.

The flow owns all routing and retry policy. These templates define the evidence supplied to each
turn, the artifact boundary, and the response contract.
