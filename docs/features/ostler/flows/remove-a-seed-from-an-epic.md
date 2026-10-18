---
type: flow
slug: remove-a-seed-from-an-epic
title: Remove a seed from an epic
---
# Remove a seed from an epic

- start: a seed is no longer in scope
- steps:
  - [ostler seed remove](../planning.md#ostler-seed-remove)
- end: the caller sees the seed removed
- verify: exit_status(code=0)
- verify: stdout(matches="^removed seed 'SD-2' from epic '0001-first'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with an epic that holds seed SD-2
