---
type: flow
title: Pick a turn to replay
---
# Pick a turn to replay

An author names one recorded [agent turn](../concepts/agent-turns.md) to replay. The run has to be
a directory on disk, the turn has to hold a valid turn.json, and a prompt has to exist to send.
Once those hold, the replay checks that the checkout still sits where the turn started.

- steps:
  - [refuse-replay-without-run](../workhorse.md#refuse-replay-without-run)
  - [refuse-replay-unknown-run](../workhorse.md#refuse-replay-unknown-run)
  - [refuse-missing-turn](../workhorse.md#refuse-missing-turn)
  - [refuse-bad-turn-record](../workhorse.md#refuse-bad-turn-record)
  - [refuse-missing-prompt](../workhorse.md#refuse-missing-prompt)
  - [refuse-missing-variant](../workhorse.md#refuse-missing-variant)
  - [refuse-zero-repeat](../workhorse.md#refuse-zero-repeat)
  - [replay](../workhorse.md#replay)
- fixture: seeded-runs
- end: the replay refuses to drop the commits made after the turn
- verify: stderr(matches="dropping every commit after it")
- detail: [agent turns](../concepts/agent-turns.md)
