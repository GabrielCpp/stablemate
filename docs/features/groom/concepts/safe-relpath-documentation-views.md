---
type: concept
slug: safe-relpath-documentation-views
title: Safe relpath documentation views
---
# Safe relpath documentation views

`safe_relpath` is declared once in `groom/groom/docker_io.py`; it rejects empty, rooted, empty-segment, and parent-traversal paths, then returns the accepted segments joined with `/`. The source has no deprecation, wrapper, alternate implementation, or call-site preference that ranks the two documentation views.

- code: groom/groom/docker_io.py::safe_relpath
- rule: The [groom Docker I/O module](groom-docker-io-module.md#safe-relpath) records `safe_relpath` among the module's callable helpers, while the [workspace volume relative-path guard](workspace-volume-relative-path-guard.md#safe-relpath) records the complete validation contract for callers constructing `/vol/...` destinations. These are complementary views of one implementation; no source-defined ranking exists.
