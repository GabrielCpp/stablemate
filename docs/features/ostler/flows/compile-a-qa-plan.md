---
type: flow
slug: compile-a-qa-plan
title: Compile a QA plan
---
# Compile a QA plan

- start: a packet lists the claims a change owes evidence for
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
  - [ostler qa compile plan](../qa.md#ostler-qa-compile-plan)
- end: the caller reads how many claims the plan holds and how many the book left without a check
- verify: exit_status(code=0)
- verify: json_path(path="owed", equals=3)
- verify: json_path(path="declared", equals=1)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
