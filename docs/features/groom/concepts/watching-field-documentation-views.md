---
type: concept
slug: watching-field-documentation-views
title: WATCHING field documentation views
---
# WATCHING field documentation views

`WATCHING` is one process-local map, with two complementary documentation views rather than two
interchangeable implementations. The state module's field view places it in groom's complete
public mutable-state inventory and defines its role as the addressing map for selection-driven
pushes. The run watch registry's field view supplies the subscription contract: its queue key,
container-id value, lifecycle, callers, and update behavior.

Read the state module view when choosing or auditing groom's shared in-memory state boundary.
Read the run watch registry view when implementing or reasoning about a tab's selected-run
subscription, addressed detail pushes, disconnect cleanup, or the live clock. Both describe the
same `groom.state.WATCHING` object; neither supersedes the other, and callers use the registry's
`watch`, `watchers_of`, and `watched_ids` helpers rather than treating either field view as a
separate storage mechanism.

- code: groom/groom/state.py::WATCHING
- rule: use the state-module field view for the public state inventory and the run-watch-registry field view for the selected-run subscription contract; both describe the same map and neither is preferred
- detail: [WATCHING field documentation views](watching-field-documentation-views.md)
