---
type: flow
title: Resume a stopped run
---
# Resume a stopped run

An operator restarts a stopped run from its checkpoint. The resume replays the command line the
run recorded in its launch.json, so a finished run, a run with no record, a contained run and a
launch.json with no resume line are all refused. Resuming is described under
[run control](../concepts/run-control.md).

- steps:
  - [refuse-resume-finished](../workhorse.md#refuse-resume-finished)
  - [refuse-resume-without-record](../workhorse.md#refuse-resume-without-record)
  - [refuse-resume-without-launch](../workhorse.md#refuse-resume-without-launch)
  - [refuse-resume-gone-pid](../workhorse.md#refuse-resume-gone-pid)
  - [refuse-resume-contained](../workhorse.md#refuse-resume-contained)
  - [refuse-resume-without-line](../workhorse.md#refuse-resume-without-line)
- fixture: seeded-runs
- end: the last refusal names the launch.json that records no resume line
- verify: stderr(matches="launch[.]json in /.*/no-line records")
- detail: [run control](../concepts/run-control.md)
