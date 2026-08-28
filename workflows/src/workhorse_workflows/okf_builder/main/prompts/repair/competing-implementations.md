### `competing-implementations` — one symbol, several same-type nodes, no ranking

Two or more nodes of the same type ground themselves in one `path::symbol`, are not related
by containment or `extends:`, and share no `detail:` concept. Each node can be entirely true
and the book still strands a reader on the one question that bites: *which one do I use?*

The answer is judgment, and judgment lives in a concept — never in a new flag on the
competitors. Repair from what the **source** already says about the preference:

- Read the cited code for evidence that the competition is settled: a deprecation
  annotation or comment, a migrated call site, one path only reachable behind a legacy
  flag, one wrapper delegating to the other. If it is, write the concept: `rule:` states
  the selection rule as prose, `prefers:` links the winning node, `deprecates:` links the
  superseded one, and the body carries the rationale and the legitimate remaining callers.
- Then point **every** competitor at it — `- detail: [<concept>](../concepts/<slug>.md)` —
  so the rule is reachable from either side rather than discoverable only by browsing.
- If the source does **not** settle it — both paths current, both reached by live call
  sites, no recorded preference — write the concept anyway, stating each side's context
  as fact, and say plainly that no ranking exists. A competition the source does not
  settle is recorded as a competition, **not resolved by invention**; picking a winner
  yourself plants a selection rule nobody made.
