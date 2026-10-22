---
type: flow
slug: retitle-a-story
title: Retitle a story
---
# Retitle a story

- start: a story's title and dependencies changed
- steps:
  - [ostler update story](../planning.md#ostler-update-story)
- end: the caller sees the story updated
- verify: exit_status(code=0)
- verify: stdout(matches="^updated story 'india' in epic '0001-first'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a story named india
