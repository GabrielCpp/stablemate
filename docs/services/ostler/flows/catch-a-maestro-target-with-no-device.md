---
type: flow
slug: catch-a-maestro-target-with-no-device
title: Catch a maestro target with no device
---
# Catch a maestro target with no device

- start: a plan declares a target whose driver is `maestro`, and the sandbox a run executes
  in has no device for `maestro hierarchy` to read
- steps:
  - [ostler qa run](../qa.md#ostler-qa-run-maestro-target)
- end: the claim that settles the screen fails before any state it names is ever checked,
  because reading the device is itself what `settle` does for a `driver="maestro"` target —
  there is no separate step where a scenario author could have caught this first
- verify: exit_status(code=1)
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md)
- fixture: [qa maestro scratch plan](../fixtures/qa-maestro-scratch-plan.md)
- detail: [Running and reporting a QA run](../concepts/running-and-reporting-a-qa-run.md)
