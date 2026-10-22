---
type: flow
slug: settle-a-story-review
title: Settle a story review
---
# Settle a story review

- start: a story's review declined its one finding with a reason
- steps:
  - [ostler edit settle review](../editing.md#ostler-edit-settle-review)
- end: the caller reads that the story is settled and finds the settlement ledger beside the resolution
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^applied: 2 file\\(s\\) changed, 0 move\\(s\\)$")
- verify: contents(subject="edit-scratch/docs/epics/0001-first/stories/sx/story.md", matches="Review fixes applied")
- verify: contents(subject="edit-scratch/art/specs/TST-01M585PFWZZXH4Y6KNMH1VK58H/review-settlement.json", matches="\"all_settled\": true")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
