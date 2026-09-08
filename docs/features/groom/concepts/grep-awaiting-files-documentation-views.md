---
type: concept
slug: grep-awaiting-files-documentation-views
title: Grep awaiting-files documentation views
---
# Grep awaiting-files documentation views

`grep_awaiting_files` has one implementation in `groom/groom/docker_io.py`: it runs the
read-only volume sweep and returns candidate paths. The two method nodes that cite it are
complementary documentation views, not alternative call targets.

Read [Groom Docker I/O module](groom-docker-io-module.md#grep-awaiting-files) for the
function's shared low-level Docker adapter contract. Read
[workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md#method-grep-awaiting-files)
when following the discovery fallback: its candidate-only result must be reread and parsed
before Groom creates a gate record. Neither view supersedes the other because callers invoke
the same function.

- rule: use the module method for the shared helper contract and the awaiting-file reader method for its workflow-discovery fallback context; both describe the same callable
