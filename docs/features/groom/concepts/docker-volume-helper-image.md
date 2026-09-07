---
type: concept
slug: docker-volume-helper-image
title: Docker volume helper image
---
# Docker volume helper image

`ALPINE_IMAGE` is the shared image selection for temporary containers that inspect, list, or
read workspace volumes. Its fixed `alpine:3.20` value supplies the BusyBox-style `find`, `grep`,
`cat`, and `cp` commands used by those helpers. `GIT_IMAGE` is a separate choice for
`git_diff`, whose temporary container must instead provide Git; it is not an alternative for
the volume operations documented here.

The module-level Alpine field is the canonical definition. The reader-specific fields retain
their command requirements so a reader can see why its use of that shared image is valid, but
they do not select distinct images.

- code: groom/groom/docker_io.py::ALPINE_IMAGE
- rule: use `ALPINE_IMAGE` for throwaway workspace-volume operations; use `GIT_IMAGE` only for the Git diff operation.
- prefers: [Groom Docker I/O module Alpine image](groom-docker-io-module.md#field-alpine-image)
