---
type: concept
slug: list-files-documentation-views
title: List-files documentation views
---
# List-files documentation views

Both nodes describe the same `list_files` implementation, not alternative runtime paths. The
module view places it among the Docker I/O adapter's public helpers; the workspace-volume reader
view records the file-tree read contract. In the implementation, the function mounts the selected
volume read-only, runs `find` below the selected base while pruning the shared skip directories,
keeps only paths below that base, and returns them sorted. It has no deprecation marker, wrapper,
or call-site selection rule that ranks these documentation views.

- rule: use the module view for the Docker I/O helper catalog and the workspace-volume reader view for the selected checkout file-list contract; neither view supersedes the other.
