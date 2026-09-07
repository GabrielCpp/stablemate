---
type: concept
slug: live-source-configuration
title: LiveSource configuration fields
---
# LiveSource configuration fields

`LiveSource` is configured by four complementary constructor fields rather than by
alternative implementations. `name` identifies the package in diagnostics, `mount` is
the read-only host bind to stage, and `root` is the container-local location for the
immutable staged generations. `with_editable` is optional and supplies additional local
packages required beside the staged package during installation.

There is no selection between these fields: every source supplies `name`, `mount`, and
`root`; `with_editable` remains empty unless the staged package needs an additional local
editable package. The source keeps the bind and generation root separate so a running
process imports a completed container-local generation rather than files being edited on
the host.

- code: `workhorse/livesource.py::LiveSource`
- rule: configure `name`, `mount`, and `root` together; add `with_editable` only for required accompanying local packages
- detail: [LiveSource documentation guide](live-source-documentation-guide.md)
