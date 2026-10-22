---
type: concept
slug: sidecar-rpc-documentation-scope
title: Sidecar RPC documentation scope
---
# Sidecar RPC documentation scope

`groom/groom/app.py::_sidecar_rpc` has one implementation. It is the sole live-sidecar entry point
the `files`, `file_content`, and diff HTTP handlers call before falling back to a local-filesystem
or Docker-volume read. There is no alternate runtime implementation or source-defined ranking
between these two documentation nodes.

Use [Sidecar RPC helper](sidecar-rpc-helper.md#method-_sidecar_rpc) for the callable's complete
signature, algorithm, and per-outcome contract. Use [Live sidecar RPC and volume fallback
selection](live-sidecar-rpc-and-volume-fallback-selection.md) for the caller-side rule that
decides, per read, whether the live socket result or the volume fallback is used. Both ground in
the same function and must remain consistent rather than being chosen as competing
implementations.

- rule: use Sidecar RPC helper for the callable contract and Live sidecar RPC and volume fallback selection for the caller-side selection rule; neither is a different implementation or a deprecated alternative.
