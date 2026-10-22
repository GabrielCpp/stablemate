---
type: flow
slug: scaffold-a-workflow
title: Scaffold a workflow
---
# Scaffold a workflow

An author starts a new workflow of their own. They name it and give the shell check that decides
when the work is done, and `workhorse-new` writes a standalone distribution beside the launch
directory.

- fixture: none, because the walk creates everything its end state observes
- start: the working directory holds no `fix-tests` folder
- verify: absent(subject="fix-tests/pyproject.toml")
- steps:
  - [new](../workhorse-new.md#new)
- end: the new distribution exists in the named folder
- verify: created(subject="fix-tests/pyproject.toml")
- detail: [workhorse-new command](../workhorse-new.md)
