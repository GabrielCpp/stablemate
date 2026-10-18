---
type: flow
slug: read-a-qa-report
title: Read a QA report
---
# Read a QA report

- start: a plan ran for a spec
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
  - [ostler qa run](../qa.md#ostler-qa-run)
  - [ostler qa report](../qa.md#ostler-qa-report)
- end: the caller reads the status of the run per scenario and obligation
- verify: exit_status(code=0)
- verify: stdout(matches="Status \\| \\*\\*PASSED\\*\\*")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-report.md", matches="PASSED")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
