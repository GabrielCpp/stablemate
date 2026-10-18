---
type: flow
slug: pull-frames-from-a-run
title: Pull frames from a run
---
# Pull frames from a run

- start: a run recorded no video
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
  - [ostler qa run](../qa.md#ostler-qa-run)
  - [ostler qa frames](../qa.md#ostler-qa-frames)
- end: the caller is told the run has no recording
- verify: exit_status(code=1)
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
