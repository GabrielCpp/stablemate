---
type: flow
slug: add-a-story-to-an-epic
title: Add a story to an epic
---
# Add a story to an epic

- start: an epic holds one story
- steps:
  - [ostler create story](../planning.md#ostler-create-story)
- end: the caller reads the created story's id and its epic
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", matches="in epic '0002-second'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with an epic that holds one story
