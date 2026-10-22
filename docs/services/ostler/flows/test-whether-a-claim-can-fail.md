---
type: flow
slug: test-whether-a-claim-can-fail
title: Test whether a claim can fail
---
# Test whether a claim can fail

- start: a book declares checks for its claims
- steps:
  - [ostler qa sensitivity](../qa.md#ostler-qa-sensitivity)
- end: the caller reads whether any declared check is insensitive
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="sensitive")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
