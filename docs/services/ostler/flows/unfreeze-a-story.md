---
type: flow
slug: unfreeze-a-story
title: Unfreeze a story
---
# Unfreeze a story

- start: a frozen story needs a rewrite
- steps:
  - [ostler unfreeze](../planning.md#ostler-unfreeze)
- end: the caller sees the story unfrozen
- verify: exit_status(code=0)
- verify: stdout(matches="^unfreeze 'echo'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a story that is frozen
