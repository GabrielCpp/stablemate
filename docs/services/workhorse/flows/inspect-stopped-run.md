---
type: flow
title: Inspect a stopped run
---
# Inspect a stopped run

An operator reads where a stopped run would pick up before deciding to rewind or resume it. The
checkpoint on disk names the flow, the state and the params, as the
[run directory](../concepts/run-directory.md) page describes. A directory with no checkpoint, or
one the retired YAML engine wrote, is refused. The decision itself belongs to
[run control](../concepts/run-control.md).

- steps:
  - [control](../workhorse.md#control)
  - [refuse-params-without-checkpoint](../workhorse.md#refuse-params-without-checkpoint)
  - [refuse-params-yaml-checkpoint](../workhorse.md#refuse-params-yaml-checkpoint)
  - [print-worktree-params](../workhorse.md#print-worktree-params)
  - [print-checkpoint-params](../workhorse.md#print-checkpoint-params)
- fixture: seeded-runs
- end: the printed checkpoint names the flow the run was in
- verify: stdout(matches="flow.: .Main.")
- detail: [run control](../concepts/run-control.md)
