---
type: flow
slug: catch-a-runbook-with-an-unknown-driver
title: Catch a runbook with an unknown driver
---
# Catch a runbook with an unknown driver

- start: a runbook names ftp as its driver
- steps:
  - [ostler doctor unknown driver](../doctor-checks.md#ostler-doctor-unknown-driver)
- end: the caller reads an error finding that lists the drivers a runbook can name and the exit status is 1
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"unknown-driver\"")
- fixture: [doctor scratch repo](../fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four books that each carry one kind of defect
