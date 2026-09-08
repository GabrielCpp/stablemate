---
type: concept
slug: workflow-unit-test-tiers
title: Workflow unit-test tiers
---
# Workflow unit-test tiers

[`workflows/Makefile::test`](../../../../workflows/Makefile) runs pytest over the complete
`tests` tree. It is the aggregate package gate, not a replacement for the focused test
commands documented by the four unit-test runbooks.

Choose [Author unit tests](../ops/author-unit-tests.md) when changing Author workflow
composition or its subflows, [OKF-builder unit tests](../ops/okf-builder-unit-tests.md) for
OKF-builder workflow boundaries, [Research unit tests](../ops/research-unit-tests.md) for the
research workflow or measurement adapter, and [Workflow shared unit
tests](../ops/workflow-shared-unit-tests.md) for cross-workflow and kit contracts. These tiers
are peers: the source records no preferred or deprecated tier, and the aggregate target runs
all of them.

- code: `workflows/Makefile::test`
- rule: select the focused tier by the workflow or shared contract under change; use the aggregate target for the complete workflow suite
