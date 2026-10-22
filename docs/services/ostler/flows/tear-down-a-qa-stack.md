---
type: flow
slug: tear-down-a-qa-stack
title: Tear down a QA stack
---
# Tear down a QA stack

- start: a book declares no runbook and no server
- steps:
  - [ostler qa stack down](../qa.md#ostler-qa-stack-down)
- end: the caller is told there is nothing to tear down
- verify: exit_status(code=0)
- verify: stdout(matches="declares no runbook")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
