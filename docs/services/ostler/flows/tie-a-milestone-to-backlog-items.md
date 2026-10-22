---
type: flow
slug: tie-a-milestone-to-backlog-items
title: Tie a milestone to backlog items
---
# Tie a milestone to backlog items

- start: a milestone delivers filed ideas
- steps:
  - [ostler milestone set source items](../planning.md#ostler-milestone-set-source-items)
- end: the caller sees the items recorded
- verify: exit_status(code=0)
- verify: stdout(matches="^set 1 source item\\(s\\) on milestone 'm1'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a milestone and a backlog item X-1
