---
type: flow
slug: open-an-epic
title: Open an epic
---
# Open an epic

- start: a plan repo holds three epics and the caller wants a fourth
- steps:
  - [ostler create epic](../planning.md#ostler-create-epic)
- end: the caller reads the new epic's directory name, numbered after the last
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="name", matches="-fourth$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with four epics, so the new one is numbered after the last
