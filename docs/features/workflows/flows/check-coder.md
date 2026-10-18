---
type: flow
slug: check-coder
title: Check workhorse-coder
---
# Check workhorse-coder

An author confirms the `workhorse-coder` command is installed and wired before trusting it with
real work. They read the engine version the script carries, render its state graph, and dry-run
the registered flow so no agent turn is spent.

- fixture: none, because the walk reads the installed command and writes nothing the end state depends on
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-coder.dot")
- steps:
  - [version](../workhorse-coder.md#version)
  - [dot](../workhorse-coder.md#dot)
  - [run](../workhorse-coder.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [workhorse-coder command](../workhorse-coder.md)
