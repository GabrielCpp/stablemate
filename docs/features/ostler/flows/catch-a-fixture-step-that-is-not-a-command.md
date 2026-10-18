---
type: flow
slug: catch-a-fixture-step-that-is-not-a-command
title: Catch a fixture step that is not a command
---
# Catch a fixture step that is not a command

- start: a fixture step holds a run line with an unterminated quote
- steps:
  - [ostler doctor unparsable step](../doctor-checks.md#ostler-doctor-unparsable-step)
- end: the caller reads the step named in an error finding and the exit status is 1
- verify: exit_status(code=1)
- verify: json_path(path="errors", equals=1)
- verify: json_path(path="findings[0].code", equals="unparsable-command")
- verify: json_path(path="findings[0].path", equals="docs/features/shell/fixtures/prepare.md")
- fixture: [doctor scratch repo](../fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four books that each carry one kind of defect
