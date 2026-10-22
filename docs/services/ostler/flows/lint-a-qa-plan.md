---
type: flow
slug: lint-a-qa-plan
title: Lint a QA plan
---
# Lint a QA plan

- start: a plan was written for a spec
- steps:
  - [ostler qa lint](../qa.md#ostler-qa-lint)
- end: the caller reads that the plan is clean
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
