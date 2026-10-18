---
type: flow
slug: record-a-qa-assertion
title: Record a QA assertion
---
# Record a QA assertion

- start: a session is open
- steps:
  - [ostler qa start](../qa.md#ostler-qa-start)
  - [ostler qa assert](../qa.md#ostler-qa-assert)
- end: the caller reads that the assertion passed
- verify: exit_status(code=0)
- verify: stdout(matches="^assert 'b': PASS$")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
