---
type: flow
slug: clear-legacy-qa-scratch
title: Clear legacy QA scratch
---
# Clear legacy QA scratch

- start: an old layout left scratch directories beside a spec
- steps:
  - [ostler qa clean](../qa.md#ostler-qa-clean)
- end: the caller reads that none were found
- verify: exit_status(code=0)
- verify: json_path(path="removed", equals=false)
- verify: json_path(path="status", equals="passed")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
