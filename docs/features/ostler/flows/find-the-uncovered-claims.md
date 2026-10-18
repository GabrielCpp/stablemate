---
type: flow
slug: find-the-uncovered-claims
title: Find the uncovered claims
---
# Find the uncovered claims

- start: a run covered one of the three claims a change owes evidence for
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
  - [ostler qa run](../qa.md#ostler-qa-run)
  - [ostler qa evidence map](../qa.md#ostler-qa-evidence-map)
- end: the caller reads the count of covered and uncovered claims
- verify: exit_status(code=1)
- verify: json_path(path="overall", equals="Pass")
- verify: json_path(path="counts.covered", equals=1)
- verify: json_path(path="counts.uncovered", equals=2)
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
