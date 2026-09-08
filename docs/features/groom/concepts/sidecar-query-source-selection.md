---
type: concept
slug: sidecar-query-source-selection
title: Sidecar query source selection
---
# Sidecar query source selection

`sidecar_query` has one implementation, but two documentation views. The method in the Docker
I/O module is the callable's API reference. The method in host-to-container sidecar query
describes the same call in discovery: it runs only after an eligible container is known to be
running, and its `None` result permits volume reconstruction.

There is no competing implementation to select. Readers needing the callable's signature,
return contract, and module-wide failure conventions should use the Docker I/O module view.
Readers deciding how discovery obtains a snapshot should use the host-to-container view. The
implementation delegates to `docker_exec` with the fixed sidecar query command and returns
`None` for the represented unavailable results, so neither view supersedes the other.

- rule: use the Docker I/O module view for the callable contract and the host-to-container view for discovery context; both describe the same `sidecar_query` implementation.
