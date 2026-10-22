---
type: flow
slug: bring-up-a-stack-with-no-probe
title: Bring up a stack with no probe
---
# Bring up a stack with no probe

- start: a runbook's one service step launches the system but declares no `entry-url:`, so
  there is nothing to poll over HTTP
- steps:
  - [ostler qa stack up](../qa.md#ostler-qa-stack-up-no-probe)
- end: bring-up trusts the launch command's own exit code instead of a probe that was never
  declared
- verify: exit_status(code=0)
- verify: stdout(matches="^stack brought up and healthy at \\(no entry url\\)$")
- fixture: [qa stack no-probe repo](../fixtures/qa-stack-no-probe-repo.md)
