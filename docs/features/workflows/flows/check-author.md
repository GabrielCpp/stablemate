---
type: flow
slug: check-author
title: Check workhorse-author
---
# Check workhorse-author

An author confirms the `workhorse-author` command is installed and wired before trusting it with
real work. They read the engine version the script carries, render its state graph, and dry-run
the registered flow so no agent turn is spent.

- fixture: none, because the walk reads the installed command and writes nothing the end state depends on
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-author.dot")
- steps:
  - [version](../workhorse-author.md#version)
  - [dot](../workhorse-author.md#dot)
  - [run](../workhorse-author.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [workhorse-author command](../workhorse-author.md)
