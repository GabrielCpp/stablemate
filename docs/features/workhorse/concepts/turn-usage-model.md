---
type: concept
slug: turn-usage-model
title: Turn usage model
---
# Turn usage model

`normalize` translates an agent CLI's raw completion event into a `TurnUsage` value. The
result is the boundary between backend-specific spellings and consumers: `TurnUsage` retains
each reported token count, cost, and duration independently, with `None` distinguishing an
unreported measurement from a reported zero.

These concepts are complementary rather than alternative implementations. Use usage
normalization when handling a raw backend event; use turn usage measurements when reading,
merging, or interpreting the canonical value. Neither supersedes the other: normalization
needs the value's measurement semantics to preserve reports faithfully, and consumers must
receive normalized values before those semantics apply.

- rule: normalize raw backend events before consuming `TurnUsage`; interpret each canonical field only as its named measurement
