---
type: concept
slug: author-epic-edit-prompt-contracts
title: Author epic edit prompt contracts
---
# Author epic edit prompt contracts

The `epic_edit` flow renders six agent turns of its own and hands the plan, the stories and the coverage to the [PM review](author-pm-review.md). Planning and review turns are read-only; deterministic
nodes validate and apply graph changes between turns. Story authoring turns write only the selected
story's artifacts, while all turns return typed JSON consumed by the next state. The feature book is
always read-only to these prompts.

- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/plan-epic-edit.md` @9bd6bedd06ce
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/refine-epic-edit-plan.md` @9c92addea733
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/rewrite-epic-edit.md` @031fe29f72ac
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/design-mockup.md` @f918719466f5
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/write-story.md` @78b80c91b824
- code: `workflows/src/workhorse_workflows/author/epic_edit/prompts/rework-story.md` @d16914d79c20
- detail: [author epic edit subflow](author-epic-edit-subflow.md)
- detail: [author PM review angles](author-pm-angles.md)

## Prompt Contracts

### Plan turns
`plan-epic-edit.md` receives the binding intent, current snapshot, epic directory, the open
records of the debt register as a listing, feature-book directory, and optional epic context. It must return one complete `EpicEditPlan`
with journey, seed, story, deletion, affected-story, and notes data. It must not edit files.

`refine-epic-edit-plan.md` receives the same baseline, the rejected plan, and coded validation
findings. It returns a complete replacement `EpicEditPlan` that fixes every finding without weakening
the requested operation or mutating files.

### Review and rewrite turns
The plan review is the PM review at the `epic-edit-plan` stage. It receives the intent, snapshot and
statically valid plan as detail and judges them from the `plan` angle. It makes no repository change.

`rewrite-epic-edit.md` receives the intent, approved plan, pre-edit snapshot, surviving epic directory,
and prior validation findings. It may rewrite only human-owned epic prose before `## Seeds`, preserving
the `Seeds` and `Stories` sections, and returns `complete` or `blocked` with notes.

### Story turns
`design-mockup.md` runs only for an affected story that lists a web or mobile service. It receives the epic, story identity and
directories, feature-book directory, and epic directory. It may write only the story-local
`mockup.html`; failure to produce it fails the edit.

`write-story.md` receives the selected story identity, epic, feature-book directory, and optional
mockup path. It writes only the story planning artifact and returns `WriteStoryResult`; a product or
scope question returns `blocked` with notes.

`rework-story.md` receives the selected story, validation or review findings, operator feedback, and
optional prior attempts and mockup path. It repairs only the named findings in the story artifact
and returns the same `WriteStoryResult` shape, including `blocked` for an unresolved scope decision.

The story review is the PM review at the `story` stage, described in [author PM review](author-pm-review.md).

### Coverage turn
The coverage review is the PM review at the `story-split` stage. It judges the epic directory after
the deterministic coverage lint passes, returns one verdict per angle, and does not edit repository
files.

The flow owns all routing and retry policy. These templates define the evidence supplied to each
turn, the artifact boundary, and the response contract.
