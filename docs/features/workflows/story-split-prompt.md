---
type: format
slug: story-split-prompt
title: Story split prompt contract
---
# Story split prompt contract

The story-split turn receives one epic and its canonical directory, reads the epic's researched
journeys, delivered experience, acceptance, seeds, context, existing stories, and the milestone
that lists the epic, and records a complete story topology through Ostler. It sizes stories from
researched seed details, claims every seed, and makes the dependency-root story a walking skeleton
for the epic's journey. Each later story must widen a runnable path and have a concrete deliverable;
layer-only work is folded into the earliest journey story that needs it.

The turn records stories with `ostler create story`, including kebab-case slugs, titles, covered
seeds, and only genuine blockers from the same epic. It does not write story bodies. On re-entry it
extends or refines the existing set without replacing stories that already have bodies, and a
rework pass must act on the supplied coverage findings or explicitly return a standoff. A first
split or addressed rework returns `complete`; an unresolved product or scope choice returns
`blocked` with the question. It does not install dependencies, run repository-wide checks, or
perform staging, commit, push, or branch operations.

- file: `workflows/src/workhorse_workflows/author/story_split/prompts/split-stories.md`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StorySplit`
- detail: [author story-split subflow](concepts/story-split-subflow.md)
- tests: `workflows/tests/author/story_split/test_flow.py::test_accepts_one_epic_graph_without_selecting_authoring_or_git`

## Fields

### epic
- type: string
- required: true
- semantics: the single epic whose stories are split and refined
- verify: json_path(path="$.epic", matches=".+")

### epic_dir
- type: string path
- required: true
- semantics: canonical directory containing the epic document and story documents to inspect
- verify: json_path(path="$.epic_dir", matches=".+")

### rework_notes
- type: string
- default: empty string
- required: true
- semantics: prior mechanical or semantic coverage findings that bind a rework pass
- verify: json_path(path="$.rework_notes", matches=".*")

The prompt treats a non-empty value as binding coverage-stage feedback. It may change the split,
merge or add stories, correct `covers`, or add real same-epic `depends` edges; it must not claim
completion without either making the requested change or returning a reasoned `standoff`.

### status
- type: string
- default: empty string
- required: true
- semantics: `complete` records the split, `standoff` declines the requested rework, and `blocked` parks a product or scope decision
- verify: json_path(path="$.status", matches="^(complete|standoff|blocked)$")

### notes
- type: string
- default: empty string
- required: true
- semantics: summary of created or refined stories, refusal rationale, or blocking question
- verify: json_path(path="$.notes", matches=".*")
