---
type: concept
slug: coder-queue-story-pick-field-roles
title: Coder queue story pick field roles
---
# Coder queue story pick field roles

`StoryPick` records one story-selection result. `story_outcome` directs the main loop: `story`
starts implementation, `done` permits pruning and merge, and `blocked` sets the epic aside.
`reason` explains each outcome, while `epic`, `progress`, and `remaining_count` preserve the
selection context and worklist snapshot across all outcomes.

When `story_outcome` is `story`, `story_path`, `spec_dir`, `story_slug`, and `story_id` identify
the selected story and its specification. They remain empty for `done` or `blocked`; `story_id`
also remains empty for books that predate minted IDs, when consumers use `story_slug` instead.
The fields are complementary parts of one result, not competing implementations.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::select_story`
- rule: read `story_outcome` before interpreting the result; use `reason`, `epic`, `progress`, and `remaining_count` for every outcome, and use the story identity and path fields only when the outcome is `story`; no field is preferred, deprecated, or a replacement for another
