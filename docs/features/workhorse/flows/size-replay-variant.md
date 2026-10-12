---
type: flow
title: Size a replay variant
---
# Size a replay variant

An author tries a reworded prompt on one recorded [agent turn](../concepts/agent-turns.md). The
variant has to fit the size budget, which defaults to twice the recorded prompt. A variant that
fits then meets the tree check. Here the checkout moved on, so the replay refuses rather than reset
away the later commits.

- steps:
  - [refuse-unsizable-variant](../workhorse.md#refuse-unsizable-variant)
  - [refuse-oversized-variant](../workhorse.md#refuse-oversized-variant)
  - [refuse-variant-over-limit](../workhorse.md#refuse-variant-over-limit)
  - [accept-variant-at-limit](../workhorse.md#accept-variant-at-limit)
  - [refuse-moved-replay](../workhorse.md#refuse-moved-replay)
- fixture: seeded-runs
- end: the replay refuses and points at a copy of the checkout
- verify: stderr(matches="Replay against a copy of the checkout")
- detail: [agent turns](../concepts/agent-turns.md)
