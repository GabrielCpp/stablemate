---
type: flow
slug: count-the-checks-a-book-exercises
title: Count the checks a book exercises
---
# Count the checks a book exercises

- start: a book of three small defects was checked
- steps:
  - [ostler doctor census](../doctor-checks.md#ostler-doctor-census)
- end: the caller reads how many finding codes fired and how many the run never entered
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^\\d+ codes defined")
- verify: stdout(matches="(?m)^\\s+\\d+ dormant-unreachable")
- fixture: [doctor scratch repo](../fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four books that each carry one kind of defect
