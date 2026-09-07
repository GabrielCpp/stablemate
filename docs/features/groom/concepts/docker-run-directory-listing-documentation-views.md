---
type: concept
slug: docker-run-directory-listing-documentation-views
title: Docker run-directory listing documentation views
---
# Docker run-directory listing documentation views

`groom/groom/docker_io.py::list_run_dirs` is one function, but it is documented from two
current contexts. The implementation itself has no legacy branch, wrapper, migration marker, or
other distinction that ranks either documentation node.

Use [Docker run-directory reader](docker-run-directory-reader.md#list-run-dirs) when the reader
needs the volume-listing contract, its workflow-discovery role, and its directory filtering
rules. Use the [Groom Docker I/O module](groom-docker-io-module.md#list-run-dirs) entry when the
reader is navigating the module's public helper surface alongside the other Docker operations.
Neither view supersedes the other: both describe the same callable for their respective reading
contexts.

- code: groom/groom/docker_io.py::list_run_dirs
- rule: use the run-directory reader for listing semantics and discovery context; use the module entry for the public Docker helper inventory; neither is preferred or deprecated
