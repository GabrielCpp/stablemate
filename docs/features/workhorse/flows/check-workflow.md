---
type: flow
title: Check a workflow
---
# Check a workflow

An author confirms a workflow is ready before it runs unattended. They list the commands, read
which engine release the script carries, render the
[state machine](../concepts/state-machine-engine.md) to look at, and dry-run the whole workflow so
every node binds without spending an agent turn. The dry run is described under
[run launch](../concepts/run-launch.md).

- fixture: seeded-runs
- start: the working directory holds no rendered graph
- verify: absent(subject="graph.dot")
- steps:
  - [show-top-level-help](../workhorse.md#show-top-level-help)
  - [version](../workhorse.md#version)
  - [print-version](../workhorse.md#print-version)
  - [dot](../workhorse.md#dot)
  - [name-the-graph](../workhorse.md#name-the-graph)
  - [render-dot-file](../workhorse.md#render-dot-file)
  - [write-dot-long-flag](../workhorse.md#write-dot-long-flag)
  - [run](../workhorse.md#run)
- end: the dry run reports every node ran its stand-in
- verify: stdout(matches="dry-run ok .* every node ran its stand-in")
- detail: [run launch](../concepts/run-launch.md)
