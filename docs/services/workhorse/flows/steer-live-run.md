---
type: flow
title: Steer a live run
---
# Steer a live run

An operator sends live verbs to a run over its control socket. When no process serves the socket,
the refusal says what the run's own record shows: finished, never started, in flight or gone. A
verb given a flag or a name it does not take is refused before any socket is tried. The verbs are
described under [run control](../concepts/run-control.md).

- steps:
  - [refuse-no-unfinished-run](../workhorse.md#refuse-no-unfinished-run)
  - [refuse-unknown-control-run](../workhorse.md#refuse-unknown-control-run)
  - [refuse-unserved-socket](../workhorse.md#refuse-unserved-socket)
  - [report-finished-run](../workhorse.md#report-finished-run)
  - [report-missing-run-record](../workhorse.md#report-missing-run-record)
  - [report-unrecorded-pid](../workhorse.md#report-unrecorded-pid)
  - [report-gone-pid](../workhorse.md#report-gone-pid)
  - [refuse-switch-cli-unserved](../workhorse.md#refuse-switch-cli-unserved)
  - [refuse-switch-cli-without-name](../workhorse.md#refuse-switch-cli-without-name)
  - [refuse-switch-profile-without-name](../workhorse.md#refuse-switch-profile-without-name)
  - [refuse-name-on-status](../workhorse.md#refuse-name-on-status)
  - [refuse-text-on-status](../workhorse.md#refuse-text-on-status)
  - [refuse-rewind-flag-on-status](../workhorse.md#refuse-rewind-flag-on-status)
  - [refuse-params-on-stop](../workhorse.md#refuse-params-on-stop)
  - [refuse-wait-on-status](../workhorse.md#refuse-wait-on-status)
  - [refuse-core-on-stop](../workhorse.md#refuse-core-on-stop)
  - [refuse-unknown-action](../workhorse.md#refuse-unknown-action)
- fixture: seeded-runs
- end: the parser lists the nine actions it accepts
- verify: stderr(matches="invalid choice: .pause. [(]choose from")
- detail: [run control](../concepts/run-control.md)
