---
type: flow
slug: map-a-change-to-the-book
title: Map a change to the book
---
# Map a change to the book

- start: a repo changed one source file since its last commit
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context)
- end: the caller holds a packet that names the changed file and the book nodes that own it
- verify: exit_status(code=0)
- verify: json_path(path="available", equals=true)
- verify: json_path(path="status", equals="passed")
- verify: json_path(path="changedCode[0].path", equals="src/demo.py")
- verify: contents(subject="qa-scratch/art/specs/s1/qa-okf-context.json", matches="\"base\": \"HEAD\"")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed source file and a plan under spec s1
