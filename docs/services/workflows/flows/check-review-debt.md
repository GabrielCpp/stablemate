---
type: flow
slug: check-review-debt
title: Check workhorse-review-debt
---
# Check workhorse-review-debt

An author confirms the `workhorse-review-debt` command is installed and wired before trusting it
with real work. They read the engine version the script carries, render its state graph, and
dry-run the registered flow so no agent turn is spent.

- fixture: none, because the walk reads the installed command and writes nothing the end state depends on
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-review-debt.dot")
- steps:
  - [version](../workhorse-review-debt.md#version)
  - [dot](../workhorse-review-debt.md#dot)
  - [run](../workhorse-review-debt.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [workhorse-review-debt command](../workhorse-review-debt.md)
