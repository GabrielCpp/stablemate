---
type: flow
slug: open-a-qa-session
title: Open a QA session
---
# Open a QA session

- start: a tester wants to drive a check by hand
- steps:
  - [ostler qa start](../qa.md#ostler-qa-start)
- end: the caller reads the run id of the open session
- verify: exit_status(code=0)
- verify: stdout(matches="^QA session started: run_id=run2, story=s2$")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
