---
type: flow
slug: bring-up-a-qa-stack
title: Bring up a QA stack
---
# Bring up a QA stack

- start: a book declares no runbook and no server
- steps:
  - [ostler qa stack up](../qa.md#ostler-qa-stack-up)
- end: the caller is told there is nothing to bring up
- verify: exit_status(code=0)
- verify: stdout(matches="declares no runbook")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
