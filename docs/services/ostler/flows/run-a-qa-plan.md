---
type: flow
slug: run-a-qa-plan
title: Run a QA plan
---
# Run a QA plan

- start: a valid plan covers a command's exit claim
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
  - [ostler qa run](../qa.md#ostler-qa-run)
- end: the caller reads a passing run and finds its ledger and evidence file in the spec directory
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- verify: json_path(path="pass_count", equals=1)
- verify: json_path(path="fail_count", equals=0)
- verify: contents(subject="qa-scratch/art/specs/s1/qa/qa-run.ndjson", matches="\"kind\": \"session_stop\"")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-evidence.json", matches="okf:docs/services/demo/cli.md#demo-greet:exits:1")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
