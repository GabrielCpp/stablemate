---
type: concept
slug: read-file-documentation-scope
title: Read-file documentation scope
---
# Read-file documentation scope

`read_file` has one implementation in `groom/groom/docker_io.py`. Its two method
nodes are complementary documentation views, not separate readers: the [Groom
Docker I/O module](groom-docker-io-module.md#read-file) records the callable with
the rest of the module, while the [workspace volume file-content
reader](workspace-volume-file-content-reader.md#read-file) records its complete
volume-read contract, effects, failure behaviour, and callers.

Use the module view when navigating the Docker I/O API as a whole. Use the
file-content reader view when choosing or understanding a volume file read. No
implementation ranking exists because both nodes ground the same `read_file`
function and describe different documentation scopes.

- rule: use the Docker I/O module method for module-level API navigation and the workspace volume file-content reader method for the complete file-read contract; neither node selects a different implementation
