---
type: concept
slug: sidecar-register-documentation-scope
title: Sidecar register documentation scope
---
# Sidecar register documentation scope

`groom/groom/sidecar_hub.py::register` has one implementation. It is the registry's
displace-and-store operation that the websocket-sidecar endpoint calls after a useful `hello`
frame identifies a container. There is no alternate runtime implementation or source-defined
ranking between these two documentation nodes.

Use [Sidecar connection registry register](sidecar-connection-registry.md#method-register) for
the callable's complete signature, algorithm, and per-outcome contract. Use [Groom sidecar hub
module](groom-sidecar-hub-module.md#method-register) when navigating the module's public member
index and its relationships to the other sidecar hub members. Both describe the same function
and must remain consistent rather than being chosen as competing implementations.

- code: groom/groom/sidecar_hub.py::register
- rule: use Sidecar connection registry for the callable contract and Groom sidecar hub module for the module-level public-member context; neither is a different implementation or a deprecated alternative.
