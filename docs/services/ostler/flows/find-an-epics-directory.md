---
type: flow
slug: find-an-epics-directory
title: Find an epic's directory
---
# Find an epic's directory

- start: a script needs an epic's directory
- steps:
  - [ostler path epic](../planning.md#ostler-path-epic)
- end: the caller reads the directory path
- verify: exit_status(code=0)
- verify: stdout(matches="^.*/plan-scratch/art/epics/0001-first$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with an epic named 0001-first
