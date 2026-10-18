---
type: flow
slug: read-the-obligations-of-a-change
title: Read the obligations of a change
---
# Read the obligations of a change

- start: a packet owes evidence for a command's claims
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
  - [ostler qa context show](../qa.md#ostler-qa-context-show)
- end: the caller reads the obligation ids the packet carries
- verify: exit_status(code=0)
- verify: stdout(matches="demo-greet:exits:1")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
