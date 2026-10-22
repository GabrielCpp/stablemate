---
type: flow
slug: migrate-qa-fixtures
title: Migrate QA fixtures
---
# Migrate QA fixtures

- start: a repo declares no app-language fixtures
- steps:
  - [ostler qa fixtures migrate](../qa.md#ostler-qa-fixtures-migrate)
- end: the caller reads that nothing needed migrating
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
