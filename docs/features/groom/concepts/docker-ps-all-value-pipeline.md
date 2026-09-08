---
type: concept
slug: docker-ps-all-value-pipeline
title: Docker ps-all value pipeline
---
# Docker ps-all value pipeline

Four nodes each ground themselves in [`docker_ps_all`](../../../../groom/groom/docker_io.py) —
three `field:` nodes on the [Docker all-container listing reader](docker-all-container-listing-reader.md)
and the `additional-docker-fields` field on the [Docker ps container row](../docker-ps-container-row.md)
format. They are not competing descriptions of one value with a winner to pick; each names a
different stage of the same one-pass call, and a reader needs all of them together rather than a
choice between them.

- code: `groom/groom/docker_io.py::docker_ps_all`
- rule: no selection exists between these four fields — each documents a different stage of
  `docker_ps_all`'s single pass, and the source does not rank one over another
- detail: [Docker ps-all documentation scope](docker-ps-all-documentation-scope.md)

In call order: [`docker-ps-all-command`](docker-all-container-listing-reader.md#field-docker-ps-all-command)
is the argv vector the reader sends to Docker before any output exists.
[`completed-stdout-lines`](docker-all-container-listing-reader.md#field-completed-stdout-lines) is
the raw stdout of that command split into lines, before any line is parsed as JSON.
[`parsed-container-entries`](docker-all-container-listing-reader.md#field-parsed-container-entries)
is the function's return value — the sequence of successfully decoded JSON values, in stdout
order. [`additional Docker fields`](../docker-ps-container-row.md#additional-docker-fields)
describes the shape of one element of that sequence: the Docker-provided keys beyond `ID` that
pass through `docker_ps_all` unvalidated and unused by workflow discovery.

The first three are stages of the same call — input, intermediate, output — and the fourth
describes the payload shape of the third's elements. None supersedes another; all four have to
be read to have the complete picture of what `docker_ps_all` sends, reads, and returns.

