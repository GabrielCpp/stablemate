---
type: flow
slug: record-a-conflict
title: Record a conflict
---
# Record a conflict

- start: a story's criteria contradict each other
- steps:
  - [ostler conflict](../planning.md#ostler-conflict)
- end: the caller sees the conflict recorded on the story
- verify: exit_status(code=0)
- verify: stdout(matches="^conflict recorded on 'TST-01M585PCD35RNCP4A5GFKC2B4C'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a story with no conflict
