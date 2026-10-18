---
type: flow
slug: reject-a-malformed-forward
title: Reject a malformed forward
---
# Reject a malformed forward

- start: the forwarder has not written its ready-file yet
- verify: absent(subject="forwarder-ready.txt")
- steps:
  - [sandbox-forwarder](../standalone-programs.md#sandbox-forwarder)
- end: a mapping entry with no host is rejected before any port binds and before the ready-file
  is written
- verify: exit_status(code=2)
- fixture: none, because the rejected mapping is passed as an environment variable, not seeded
  state
- detail: [Sandbox port forwarding](../concepts/sandbox-port-forwarding.md)
