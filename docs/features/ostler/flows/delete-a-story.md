---
type: flow
slug: delete-a-story
title: Delete a story
---
# Delete a story

- start: a story was planned by mistake
- steps:
  - [ostler delete story](../planning.md#ostler-delete-story)
- end: the caller sees the story and its epic named
- verify: exit_status(code=0)
- verify: stdout(matches="^deleted story 'sx' from epic '0002-second'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with an epic holding one story
