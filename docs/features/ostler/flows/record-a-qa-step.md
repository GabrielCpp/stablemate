---
type: flow
slug: record-a-qa-step
title: Record a QA step
---
# Record a QA step

- start: a session is open
- steps:
  - [ostler qa start](../qa.md#ostler-qa-start)
  - [ostler qa step](../qa.md#ostler-qa-step)
- end: the caller reads that the step is recorded
- verify: exit_status(code=0)
- verify: stdout(matches="^step 'a' recorded$")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
