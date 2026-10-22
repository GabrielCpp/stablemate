---
type: concept
slug: is-running-documentation-scope
title: Is-running documentation scope
---
# Is-running documentation scope

`groom/groom/docker_io.py::is_running` is the sole running-state check implementation. It calls
`docker_inspect` once and reads only the nested `State.Running` value; there is no alternate
runtime implementation or source-defined ranking between these two documentation nodes.

Use [container running-state check](container-running-state-check.md#is-running) for the
callable's complete input, lookup, defaulting, and failure-boundary contract. Use [Groom Docker
I/O module](groom-docker-io-module.md#is-running) when navigating the module's public helper
inventory and its relationships to the other Docker operations. Both describe the same function
and must remain consistent rather than being chosen as competing implementations.

- rule: use container running-state check for the callable contract and Groom Docker I/O module for the module-level public-helper context; neither is a different implementation or a deprecated alternative.
