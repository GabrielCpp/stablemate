---
type: concept
slug: clients-field-documentation-views
title: Clients field documentation views
---
# Clients field documentation views

`groom/groom/state.py::CLIENTS` declares one process-local `set[asyncio.Queue]`; it is not two
implementations. The two field nodes document that same set from different, current contexts.

Read [dashboard client queue set](dashboard-client-queue-set.md#field-client-set) when deciding
how dashboard websocket queues are registered, removed, and included in broadcasts. Read [groom
state module](groom-state-module.md#field-clients) when locating `CLIENTS` in the module's complete
public mutable-state inventory alongside the other state containers. Neither view supersedes the
other: they address different reader questions about the one declaration.

- rule: use the queue-set field for queue membership and delivery semantics; use the state-module field for the module-level public-member inventory.
