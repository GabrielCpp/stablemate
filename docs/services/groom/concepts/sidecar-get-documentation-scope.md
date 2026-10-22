---
type: concept
slug: sidecar-get-documentation-scope
title: Sidecar get documentation scope
---
# Sidecar get documentation scope

`groom/groom/sidecar_hub.py::get` has one implementation. It is the registry's keyed lookup
that HTTP file-tree, file-content, diff, and reload handlers call to find the current sidecar
connection for a container id before falling back to Docker-volume reads. There is no alternate
runtime implementation or source-defined ranking between these two documentation nodes.

Use [Sidecar connection registry get](sidecar-connection-registry.md#method-get) for the
callable's complete signature, algorithm, and per-outcome contract. Use [Groom sidecar hub
module](groom-sidecar-hub-module.md#method-get) when navigating the module's public member index
and its relationships to the other sidecar hub members. Both describe the same function and must
remain consistent rather than being chosen as competing implementations.

- code: groom/groom/sidecar_hub.py::get
- rule: use Sidecar connection registry for the callable contract and Groom sidecar hub module for the module-level public-member context; neither is a different implementation or a deprecated alternative.
