---
type: concept
slug: docker-exec-documentation-scope
title: Docker exec documentation scope
---
# Docker exec documentation scope

`groom/groom/docker_io.py::docker_exec` is the sole host-to-container Docker exec
implementation. It constructs the tokenized command and delegates it to the subprocess runner;
`sidecar_query` is its in-module caller for the live sidecar query. There is no alternate runtime
implementation or source-defined ranking between these two documentation nodes.

Use [Docker exec runner](docker-exec-runner.md#docker_exec) for the callable's complete argv,
error, and result contract. Use [Groom Docker I/O module](groom-docker-io-module.md#docker-exec)
when navigating the module's public helper inventory and its relationships to the other Docker
operations. Both describe the same function and must remain consistent rather than being chosen
as competing implementations.

- code: groom/groom/docker_io.py::docker_exec
- rule: use Docker exec runner for the callable contract and Groom Docker I/O module for the module-level public-helper context; neither is a different implementation or a deprecated alternative.
