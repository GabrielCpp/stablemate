---
type: flow
slug: repair-a-page-with-fixable-drift
title: Repair a page with fixable drift
---
# Repair a page with fixable drift

- start: an endpoint cites its test in a verify bullet
- steps:
  - [ostler autofix check](../editing.md#ostler-autofix-check)
  - [ostler autofix](../editing.md#ostler-autofix)
- end: the caller reads that the page was repaired and finds the citation under a tests bullet
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^fixed: docs/features/demo/api\\.md$")
- verify: contents(subject="edit-scratch/docs/features/demo/api.md", matches="- tests: .src/test_demo\\.py::test_submit")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
