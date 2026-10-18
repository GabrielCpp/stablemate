---
type: flow
slug: catch-a-malformed-id-registry
title: Catch a malformed id registry
---
# Catch a malformed id registry

- start: an id registry holds a prefix that is a number
- steps:
  - [ostler doctor malformed ids](../doctor-checks.md#ostler-doctor-malformed-ids)
- end: the caller reads a warning that names the prefix and the exit status is 0
- verify: exit_status(code=0)
- verify: json_path(path="warnings", equals=1)
- verify: json_path(path="findings[0].code", equals="schema")
- fixture: [doctor scratch repo](../fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four books that each carry one kind of defect
