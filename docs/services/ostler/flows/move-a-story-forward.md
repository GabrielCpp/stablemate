---
type: flow
slug: move-a-story-forward
title: Move a story forward
---
# Move a story forward

- start: a story is Not started
- steps:
  - [ostler set status](../planning.md#ostler-set-status)
- end: the caller sees the new status confirmed
- verify: exit_status(code=0)
- verify: stdout(matches="^status of 'TST-01M585P8MYP5WJAMJ89Z981GEG'")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a story whose status is Not started
