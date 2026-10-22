---
type: flow
slug: check-loop-runner
title: Check workhorse-loop-runner
---
# Check workhorse-loop-runner

An author confirms the `workhorse-loop-runner` command is installed and wired before trusting it with
real work. They read the engine version the script carries, render its state graph, and dry-run
the registered flow so no agent turn is spent.

- fixture: none, because the walk reads the installed command and writes nothing the end state depends on
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-loop-runner.dot")
- steps:
  - [version](../workhorse-loop-runner.md#version)
  - [dot](../workhorse-loop-runner.md#dot)
  - [run](../workhorse-loop-runner.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [workhorse-loop-runner command](../workhorse-loop-runner.md)
