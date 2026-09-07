---
type: concept
slug: docker-inspect-documentation-scope
title: Docker inspect documentation scope
---
# Docker inspect documentation scope

Both method nodes describe the same `docker_inspect` function in `groom/groom/docker_io.py`.
They are complementary documentation views, not alternative implementations: the source declares
one helper, and `is_running` calls that helper directly.

Read [Docker inspection reader](docker-inspection-reader.md#docker-inspect) for the complete
single-container inspection contract, parsing boundary, and consumers. Read the
[Groom Docker I/O module](groom-docker-io-module.md#docker-inspect) entry when comparing this
helper with the module's other public Docker operations and shared return conventions. Neither
view is preferred or deprecated; the source records no implementation ranking or legacy path.

- rule: use the dedicated reader for inspection-specific behavior and consumers, or the module entry for its place among Docker I/O helpers; neither is a preferred implementation.
