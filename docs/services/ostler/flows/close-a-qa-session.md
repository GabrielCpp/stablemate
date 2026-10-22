---
type: flow
slug: close-a-qa-session
title: Close a QA session
---
# Close a QA session

- start: a session recorded a step and an assertion
- steps:
  - [ostler qa start](../qa.md#ostler-qa-start)
  - [ostler qa step](../qa.md#ostler-qa-step)
  - [ostler qa assert](../qa.md#ostler-qa-assert)
  - [ostler qa stop](../qa.md#ostler-qa-stop)
- end: the caller reads the verdict of the run
- verify: exit_status(code=0)
- verify: stdout(matches="^QA run complete: PASS")
- verify: contents(subject="qa-scratch/art/specs/s2/qa/qa-run.ndjson", matches="session_stop")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
