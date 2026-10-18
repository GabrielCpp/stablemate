---
type: flow
slug: catch-a-component-the-browser-cannot-drive
title: Catch a component the browser cannot drive
---
# Catch a component the browser cannot drive

- start: a screen names a component by description, presses a key that does not exist and answers a dialog with neither accept nor dismiss
- steps:
  - [ostler doctor ui defects](../doctor-checks.md#ostler-doctor-ui-defects)
- end: the caller reads one error finding per defect and the exit status is 1
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"prose-name\"")
- verify: stdout(matches="\"code\": \"unparsed-check\"")
- verify: stdout(matches="\"code\": \"unparsable-bullet-value\"")
- fixture: [doctor scratch repo](../fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four books that each carry one kind of defect
