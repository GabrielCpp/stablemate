---
type: concept
slug: docker-start-documentation-scope
title: Docker start documentation scope
---
# Docker start documentation scope

`docker_start` has one implementation, not two runtime alternatives. The [Groom Docker I/O module
method](groom-docker-io-module.md#docker-start) is the reference for its general Docker command,
timeout, return value, and exception contract. The [stopped container start fallback](stopped-container-start-fallback.md#docker-start)
is the reference when gate answering has already written an answer and its caller has found the
container stopped; it adds that caller's sequencing and operator-facing outcomes.

The implementation itself does not choose between these documentation views: `docker_start` always
issues one `docker start` command, while `is_running` identifies the normal path as an in-place wake
that skips a start for running containers. Neither node is deprecated or preferred globally; select
the detail that matches whether the question is about the helper contract or the gate-answer fallback.

- rule: use the Docker I/O method for the helper contract and the stopped-container fallback for the gate-answering context; neither is a replacement for the other
