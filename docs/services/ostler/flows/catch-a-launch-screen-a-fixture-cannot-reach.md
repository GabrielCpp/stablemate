---
type: flow
slug: catch-a-launch-screen-a-fixture-cannot-reach
title: Catch a launch screen a fixture cannot reach
---
# Catch a launch screen a fixture cannot reach

- start: a fixture names a launch screen for a screen page that states no lifetime
- steps:
  - [ostler doctor launch screen](../doctor-checks.md#ostler-doctor-launch-screen)
- end: the caller reads the fixture named in an error finding and the exit status is 1
- verify: exit_status(code=1)
- verify: stdout(matches="\"code\": \"fixture-launch-screen-lifetime\"")
- fixture: [doctor scratch repo](../fixtures/doctor-scratch-repo.md) with a doctor scratch repo of four books that each carry one kind of defect
