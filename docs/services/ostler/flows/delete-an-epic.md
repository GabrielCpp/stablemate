---
type: flow
slug: delete-an-epic
title: Delete an epic
---
# Delete an epic

- start: an epic was planned by mistake
- steps:
  - [ostler delete epic](../planning.md#ostler-delete-epic)
- end: the caller sees the epic deleted
- verify: exit_status(code=0)
- verify: stdout(matches="^deleted epic '0004-junk'")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with an epic named 0004-junk with no story
