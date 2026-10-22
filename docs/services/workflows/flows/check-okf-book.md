---
type: flow
slug: check-okf-book
title: Check workhorse-okf-book
---
# Check workhorse-okf-book

An author confirms the `workhorse-okf-book` command is installed and wired before trusting it with
real work. They read the engine version the script carries, render its state graph, and dry-run
the registered flow so no agent turn is spent.

- fixture: none, because the walk reads the installed command and writes nothing the end state depends on
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-okf-book.dot")
- steps:
  - [version](../workhorse-okf-book.md#version)
  - [dot](../workhorse-okf-book.md#dot)
  - [run](../workhorse-okf-book.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [workhorse-okf-book command](../workhorse-okf-book.md)
