---
type: flow
title: Fix a launch's inputs
---
# Fix a launch's inputs

An author hands a workflow its params and its context manifest, and gets the files or their JSON
wrong. Each refusal names the flag and the file at fault, and the author fixes them until a dry run
binds. How params and the manifest reach a run is in [run launch](../concepts/run-launch.md).

- steps:
  - [refuse-unreadable-params-file](../workhorse.md#refuse-unreadable-params-file)
  - [refuse-params-not-json](../workhorse.md#refuse-params-not-json)
  - [refuse-params-file-not-object](../workhorse.md#refuse-params-file-not-object)
  - [refuse-params-not-object](../workhorse.md#refuse-params-not-object)
  - [refuse-missing-context-file](../workhorse.md#refuse-missing-context-file)
  - [refuse-context-not-json](../workhorse.md#refuse-context-not-json)
  - [refuse-context-not-object](../workhorse.md#refuse-context-not-object)
  - [run](../workhorse.md#run)
- fixture: seeded-runs
- end: the launch with its inputs fixed binds every node
- verify: stdout(matches="ok .* every node")
- detail: [run launch](../concepts/run-launch.md)
