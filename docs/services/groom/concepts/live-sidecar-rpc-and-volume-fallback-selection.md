---
type: concept
slug: live-sidecar-rpc-and-volume-fallback-selection
title: Live sidecar RPC and volume fallback selection
---
# Live sidecar RPC and volume fallback selection

Workspace file-list, file-content, and diff reads have two current data paths.
The live path reads through the connected sidecar, which has the workflow's current
workspace view. The fallback reads the workflow workspace volume when a live result
is unavailable, so dashboard reads remain usable during startup, after disconnect,
or for workflows without a current sidecar connection.

The HTTP handlers call `_sidecar_rpc` first for each read. A missing connection or
`SidecarError` produces `None`; only that result selects the local-filesystem or
Docker-volume reader. A successful live result is returned directly and does not
consult the volume reader.

- code: groom/groom/app.py::_sidecar_rpc
- rule: prefer the live sidecar RPC for workspace reads; use the volume reader only when the RPC has no current connection or fails with a sidecar error
- prefers: [sidecar live session sync](../flows/sidecar-live-session-sync.md)
- detail: [Sidecar RPC documentation scope](sidecar-rpc-documentation-scope.md)
