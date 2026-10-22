---
type: concept
slug: pruned-backlog-counters
title: Pruned backlog counters
---
# Pruned backlog counters

`Pruned` in `workflows/src/workhorse_workflows/author/shared/schemas/main.py` reports two
complementary outcomes of one story-mode backlog-pruning operation. `removed` is the number of
backlog bullets the operation removed; `remaining` is the number still in the backlog afterwards.

The counters are not competing implementations and neither ranks above the other. Read `removed`
to learn the operation's mutation, and read `remaining` to learn the post-pruning backlog state;
read both when a caller needs the complete result.

- rule: use `removed` for the number of backlog bullets pruned and `remaining` for the number left after pruning; neither field substitutes for the other
