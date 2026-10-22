---
type: flow
slug: check-a-page-for-fixable-drift
title: Check a page for fixable drift
---
# Check a page for fixable drift

- start: an endpoint cites its test in a verify bullet
- steps:
  - [ostler autofix check](../editing.md#ostler-autofix-check)
- end: the caller reads which page carries drift and that the exit status is 1
- verify: exit_status(code=1)
- verify: stdout(matches="(?m)^would fix: docs/services/demo/api\\.md$")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
