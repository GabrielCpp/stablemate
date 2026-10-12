---
type: flow
title: Rewind a failed run
---
# Rewind a failed run

An operator moves a stopped run's checkpoint back to an earlier state. Only a run that failed or
never finished can be rewound, and the checkpoint has to be one this workflow's engine wrote. Each
refusal leaves the checkpoint as it was. Rewinding is described under
[run control](../concepts/run-control.md), and the checkpoint under
[run directory](../concepts/run-directory.md).

- steps:
  - [refuse-core-on-rewind](../workhorse.md#refuse-core-on-rewind)
  - [refuse-rewind-with-name](../workhorse.md#refuse-rewind-with-name)
  - [refuse-rewind-without-to](../workhorse.md#refuse-rewind-without-to)
  - [refuse-rewind-finished](../workhorse.md#refuse-rewind-finished)
  - [refuse-rewind-without-record](../workhorse.md#refuse-rewind-without-record)
  - [refuse-param-without-equals](../workhorse.md#refuse-param-without-equals)
  - [refuse-rewind-unknown-flow](../workhorse.md#refuse-rewind-unknown-flow)
  - [refuse-rewind-without-checkpoint](../workhorse.md#refuse-rewind-without-checkpoint)
  - [refuse-rewind-yaml-checkpoint](../workhorse.md#refuse-rewind-yaml-checkpoint)
- fixture: seeded-runs
- end: the last refusal leaves the YAML-era checkpoint unchanged
- verify: stderr(matches="checkpoint unchanged: .* retired YAML engine")
- detail: [run control](../concepts/run-control.md)
