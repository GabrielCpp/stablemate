---
type: flow
slug: name-the-unnamed-backlog-items
title: Name the unnamed backlog items
---
# Name the unnamed backlog items

- start: a backlog holds a bullet written by hand
- steps:
  - [ostler backlog adopt](../planning.md#ostler-backlog-adopt)
- end: the caller reads how many bullets received an id
- verify: exit_status(code=0)
- verify: stdout(matches="^adopted 1 unnamed backlog items$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with one unnamed backlog bullet
