---
type: flow
slug: check-research
title: Check workhorse-research
---
# Check workhorse-research

An author confirms the `workhorse-research` command is installed and wired before trusting it with
real work. They read the engine version the script carries, render its state graph, and dry-run
the registered flow so no agent turn is spent.

- fixture: none, because the walk reads the installed command and writes nothing the end state depends on
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-research.dot")
- steps:
  - [version](../workhorse-research.md#version)
  - [dot](../workhorse-research.md#dot)
  - [run](../workhorse-research.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [workhorse-research command](../workhorse-research.md)
