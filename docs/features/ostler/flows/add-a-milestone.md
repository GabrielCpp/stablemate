---
type: flow
slug: add-a-milestone
title: Add a milestone
---
# Add a milestone

- start: a plan repo holds one milestone
- steps:
  - [ostler create milestone](../planning.md#ostler-create-milestone)
- end: the caller reads the created milestone's name
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="name", equals="m2")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with one milestone
