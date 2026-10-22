---
type: concept
slug: sidecar-unregister-documentation-scope
title: Sidecar unregister documentation scope
---
# Sidecar unregister documentation scope

`groom/groom/sidecar_hub.py::unregister` has one implementation. It is the registry's
conditional-remove operation: the [websocket-sidecar](../http/groom.md#websocket-sidecar)
endpoint calls it on socket cleanup, and it drops a connection only while it is still the
current one for its container id, so a late close from an already-superseded socket cannot
evict a newer reconnect. There is no alternate runtime implementation or source-defined
ranking between these two documentation nodes.

Use [Sidecar connection registry unregister](sidecar-connection-registry.md#method-unregister)
for the callable's complete signature, algorithm, and per-outcome contract. Use [Groom sidecar
hub module](groom-sidecar-hub-module.md#method-unregister) when navigating the module's public
member index and its relationships to the other sidecar hub members. Both describe the same
function and must remain consistent rather than being chosen as competing implementations.

- code: groom/groom/sidecar_hub.py::unregister
- rule: use Sidecar connection registry for the callable contract and Groom sidecar hub module for the module-level public-member context; neither is a different implementation or a deprecated alternative.

