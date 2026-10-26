---
type: flow
slug: catch-a-scenario-that-outruns-its-timeout
title: Catch a scenario that outruns its timeout
---
# Catch a scenario that outruns its timeout

- start: a scenario's body goes silent for longer than its own declared `timeout=`
- steps:
  - [ostler qa run](../qa.md#ostler-qa-run-scenario-timeout)
- end: the runner kills the scenario and retires any session record the kill leaves
  mid-start, before the run ever reports the scenario failed
- verify: exit_status(code=1)
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md)
- fixture: [qa timeout scratch plan](../fixtures/qa-timeout-scratch-plan.md)
- detail: [Running and reporting a QA run](../concepts/running-and-reporting-a-qa-run.md)
