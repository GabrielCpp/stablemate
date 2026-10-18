---
type: flow
slug: read-the-check-vocabulary
title: Read the check vocabulary
---
# Read the check vocabulary

- start: the caller needs the signature of the check a claim should use
- steps:
  - [ostler checks](../book-checks.md#ostler-checks)
  - [ostler checks NAME](../book-checks.md#ostler-checks-one)
- end: the caller reads the named check's signature
- verify: exit_status(code=0)
- verify: stdout(matches="exit_status\\(code\\*=<int>\\)")
- fixture: none, because the vocabulary is fixed in code and reads no book
