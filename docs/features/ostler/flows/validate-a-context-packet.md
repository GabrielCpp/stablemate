---
type: flow
slug: validate-a-context-packet
title: Validate a context packet
---
# Validate a context packet

- start: a packet was built for a spec
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
  - [ostler qa context validate](../qa.md#ostler-qa-context-validate)
- end: the caller reads that the packet is valid
- verify: exit_status(code=0)
- verify: stdout(matches="^Context is valid\\.$")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
