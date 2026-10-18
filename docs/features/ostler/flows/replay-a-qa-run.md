---
type: flow
slug: replay-a-qa-run
title: Replay a QA run
---
# Replay a QA run

- start: a run left a ledger
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
  - [ostler qa run](../qa.md#ostler-qa-run)
  - [ostler qa replay](../qa.md#ostler-qa-replay)
- end: the caller reads a shell script that repeats the run's steps
- verify: exit_status(code=0)
- verify: stdout(matches="^#!/usr/bin/env bash")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
