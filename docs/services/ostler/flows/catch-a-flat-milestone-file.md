---
type: flow
slug: catch-a-flat-milestone-file
title: Catch a flat milestone file
---
# Catch a flat milestone file

- start: a milestone is filed as a single markdown file instead of its own folder
- steps:
  - [ostler doctor on a flat milestone file](../doctor-checks.md#ostler-doctor-milestone-layout)
- end: the caller reads one finding naming the file to move, and the exit status stops a gate
- verify: exit_status(code=1)
- verify: json_path(path="errors", equals=1)
- fixture: [doctor scratch repo](../fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four
  books that each carry one kind of defect
