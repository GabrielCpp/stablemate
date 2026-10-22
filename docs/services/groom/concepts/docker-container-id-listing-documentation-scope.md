---
type: concept
slug: docker-container-id-listing-documentation-scope
title: Docker container-id listing documentation scope
---
# Docker container-id listing documentation scope

`list_container_ids` has one implementation in `groom/groom/docker_io.py::list_container_ids`:
it runs `docker ps -aq`, returns normalized short ids after a successful process, and returns
`None` for a non-zero Docker exit. The Docker container-id listing reader records that callable's
complete contract; the Groom Docker I/O module records the same method in its module-wide public
helper inventory.

Neither documentation context is preferred or deprecated. Read the dedicated reader for the
callable's Docker-listing behavior and prune-safety distinction, and read the module entry when
navigating the adapter's public helpers and their relationships. Both describe the same function
and must remain consistent rather than being chosen as alternative implementations.

- rule: select the documentation context by the question being answered; `list_container_ids` has one current implementation and no ranking between the dedicated reader and module-wide views
