---
type: flow
slug: validate-a-qa-plan
title: Validate a QA plan
---
# Validate a QA plan

- start: a plan covers the claims of a packet
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
  - [ostler qa validate](../qa.md#ostler-qa-validate)
- end: the caller reads that the plan is valid
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
