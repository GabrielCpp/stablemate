---
type: concept
slug: docker-command-timeout
title: Docker command timeout
---
# Docker command timeout

`DOCKER_TIMEOUT` is the module-wide default timeout for a completed Docker subprocess. The
shared runner applies its 20-second default whenever a caller does not supply a timeout; the
Docker exec helper is the exception because its caller may provide an explicit timeout.

The fields on volume readers and the module describe that same constant in the context of their
respective operations. They are not alternative implementations and no ranking exists among
them: use the reader's field to understand that reader's command boundary, or the module field
to understand the default across Docker I/O.

- code: groom/groom/docker_io.py::DOCKER_TIMEOUT
- rule: use the shared 20-second default for Docker I/O calls without an explicit timeout; use the reader-specific field only for the operation-specific timeout boundary
