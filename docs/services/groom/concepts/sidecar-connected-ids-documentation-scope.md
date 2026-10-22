---
type: concept
slug: sidecar-connected-ids-documentation-scope
title: Sidecar connected ids documentation scope
---
# Sidecar connected ids documentation scope

`groom/groom/sidecar_hub.py::connected_ids` has one implementation. It is the registry's
key-snapshot method: the [post-reload endpoint](../http/groom.md#post-reload) calls it to
enumerate current targets before sending reload frames. There is no alternate runtime
implementation or source-defined ranking between these two documentation nodes.

Use [Sidecar connection registry connected ids](sidecar-connection-registry.md#method-connected-ids)
for the callable's complete signature, algorithm, and per-outcome contract. Use [Groom sidecar hub
module](groom-sidecar-hub-module.md#method-connected-ids) when navigating the module's public
member index and its relationships to the other sidecar hub members. Both describe the same
function and must remain consistent rather than being chosen as competing implementations.

- code: groom/groom/sidecar_hub.py::connected_ids
- rule: use Sidecar connection registry for the callable contract and Groom sidecar hub module for the module-level public-member context; neither is a different implementation or a deprecated alternative.
