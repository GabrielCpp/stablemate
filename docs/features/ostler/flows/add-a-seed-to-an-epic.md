---
type: flow
slug: add-a-seed-to-an-epic
title: Add a seed to an epic
---
# Add a seed to an epic

- start: an epic needs a unit of source to cover
- steps:
  - [ostler seed add](../planning.md#ostler-seed-add)
- end: the caller sees the seed added
- verify: exit_status(code=0)
- verify: stdout(matches="^added seed 'SD-9' in epic '0002-second'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with an epic with no seed
