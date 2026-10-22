---
type: concept
slug: repository-picker-flow-selection
title: Repository picker flow selection
---
# Repository picker flow selection

`GET /repos` is the shared repository-picker read used before either workspace
file browsing or working-tree diff inspection. It enumerates checkout directories
for every workflow with a known workspace volume and returns the same grouped
container and checkout entries to both dashboard paths.

These flows are not competing implementations and neither supersedes the other.
Choose the workspace-file flow when the operator needs a file tree and file
contents; choose the working-tree-diff flow when the operator needs uncommitted
changes. Both legitimately request the picker when no repository is selected,
because the picker supplies the container and checkout context their distinct
read endpoints require.

- code: groom/groom/app.py::repos
- rule: use workspace-file browsing to inspect repository files and working-tree diff inspection to inspect uncommitted changes; both use the same repository picker and neither is preferred or deprecated
