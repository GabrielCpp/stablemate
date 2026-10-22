---
type: flow
slug: list-the-qa-tools
title: List the QA tools
---
# List the QA tools

- start: a repo opts into a QA tool in its config
- steps:
  - [ostler qa tools list](../qa.md#ostler-qa-tools-list)
- end: the caller reads the tool, its command and whether it resolves
- verify: exit_status(code=0)
- verify: stdout(matches="^demo \\(echo\\) \\[ok\\]")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
