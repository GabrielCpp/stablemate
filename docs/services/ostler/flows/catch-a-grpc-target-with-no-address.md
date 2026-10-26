---
type: flow
slug: catch-a-grpc-target-with-no-address
title: Catch a gRPC target with no address
---
# Catch a gRPC target with no address

- start: a scenario calls `qa.grpc` on a target whose `base_url` names no address
- steps:
  - [ostler qa run](../qa.md#ostler-qa-run-grpc-target)
- end: the call is refused before it ever reaches a server, because the client needs an
  address before it can make any call at all — there is no separate step where a scenario
  author could have caught this first
- verify: exit_status(code=1)
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md)
- fixture: [qa grpc scratch plan](../fixtures/qa-grpc-scratch-plan.md)
- detail: [Running and reporting a QA run](../concepts/running-and-reporting-a-qa-run.md)
